from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from loguru import logger
from sqlalchemy import select

from app.api.routes import (
    admin, announcements, auth, badges, bottles, browse_history, circle_apply, circles, checkin,
    comments, deepseek, feedback, follows, images, interactions, match, messages, notifications,
    polls, posts, schools, search, stats, topics, users, ws,
)
from app.core.config import get_settings
from app.core.database import Base, SessionLocal, engine
from app.core.errors import ErrorCode, error_response, get_error_message, pydantic_error_to_code
from app.core.logger import setup_logger
from app.models import Announcement, Badge, Category, CategoryAdmin, School, SeedInviteCode, WarningConfig, WarningLog  # noqa: F401  保证模型注册到 Base.metadata

setup_logger()
settings = get_settings()
app = FastAPI(title=settings.app_name)

# GZip 压缩：显著减小 JS/CSS/HTML 传输体积（1.1MB 主包压缩后约 300KB）
app.add_middleware(GZipMiddleware, minimum_size=1024)

# 允许的前端来源：本地 + .env 中配置的额外域名（内网穿透/外网部署）
_allowed_origins = [settings.frontend_origin]
if settings.extra_origins:
    _allowed_origins.extend(
        [o.strip() for o in settings.extra_origins.split(",") if o.strip()]
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    # T7-12：生产收紧 CORS，明确允许的方法和头，避免 TRACE/CONNECT 等危险方法
    allow_methods=["GET", "POST", "PATCH", "DELETE", "PUT"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.middleware("http")
async def rewrite_api_prefix(request: Request, call_next):
    """将前端 /api/* 请求去掉 /api 前缀，匹配后端路由（生产环境无 Vite proxy）。

    稳定性修复：浏览器直接导航到 /api/* URL（如地址栏输入、收藏夹、自动补全）时，
    不重写路径 → 不命中 API 路由 → SPA fallback 返回 index.html → Vue Router 接管。
    避免「页面显示原始 JSON」的稳定性问题。

    判定方式：浏览器导航请求 Accept 头包含 text/html；
    AJAX 请求（axios/fetch）Accept 头为 application/json 或 */*（不带 text/html 优先）。
    """
    path = request.url.path
    if path.startswith("/api/") or path == "/api":
        accept = request.headers.get("accept", "")
        # 浏览器导航：Accept 包含 text/html → 不重写，交给 SPA fallback
        if "text/html" in accept:
            pass
        else:
            # AJAX 请求：去掉 /api 前缀
            new_path = path[4:] if len(path) > 4 else "/"
            scope = request.scope
            scope["path"] = new_path
            scope["raw_path"] = new_path.encode("utf-8")
    return await call_next(request)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    # exc.detail 可以是 int（错误码）或 str（旧式消息）
    if isinstance(exc.detail, int):
        code = exc.detail
        msg = get_error_message(code)
    else:
        # 兼容字符串 detail（如 AI 审核返回的动态原因）
        code_map = {401: ErrorCode.NOT_LOGGED_IN, 403: ErrorCode.NO_PERMISSION, 404: ErrorCode.UNKNOWN_ERROR, 429: ErrorCode.LOGIN_LOCKED}
        code = code_map.get(exc.status_code, ErrorCode.UNKNOWN_ERROR)
        msg = str(exc.detail)
    logger.warning("[HTTP_EXC] status={} code={} msg={}", exc.status_code, code, msg)
    return JSONResponse(status_code=200, content={"code": code, "msg": msg, "data": {}})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    code = pydantic_error_to_code(errors)
    msg = get_error_message(code)
    # Pydantic 校验错误中 ctx 可能含 ValueError 等不可 JSON 序列化的对象，
    # 提取错误消息字符串后再返回，避免 TypeError: Object of type ValueError is not JSON serializable
    safe_errors = []
    for err in errors:
        safe_err = {
            "loc": err.get("loc"),
            "msg": err.get("msg"),
            "type": err.get("type"),
        }
        ctx = err.get("ctx")
        if ctx:
            # ctx 中的异常对象转为字符串
            safe_ctx = {k: (str(v) if isinstance(v, BaseException) else v) for k, v in ctx.items()}
            safe_err["ctx"] = safe_ctx
        safe_errors.append(safe_err)
    # value_error 是自定义校验器抛出的（如图片 URL 协议非法），用具体 msg 替代通用 "参数错误"
    # 让前端 ElMessage 直接展示更有用的错误信息。
    if errors and errors[0].get("type") == "value_error":
        first_msg = errors[0].get("msg", "")
        # Pydantic 的 msg 形如 "Value error, 图片 URL 不允许使用该协议"
        if first_msg.startswith("Value error, "):
            first_msg = first_msg[len("Value error, "):]
        if first_msg:
            msg = first_msg
    logger.warning("[VALIDATION_ERR] code={} msg={} errors={}", code, msg, safe_errors)
    return JSONResponse(status_code=200, content={"code": code, "msg": msg, "data": {"errors": safe_errors}})


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("[UNHANDLED] {}", exc)
    return JSONResponse(status_code=200, content=error_response(ErrorCode.UNKNOWN_ERROR))


@app.on_event("startup")
def startup() -> None:
    # T2-4：生产环境必须修改 jwt_secret 默认值，否则启动失败（防止 JWT 被伪造，S4）
    if settings.env != "dev" and settings.jwt_secret == "change-me":  # nosec B105
        raise RuntimeError(
            "[FATAL] 生产环境 (ENV != dev) 必须修改 JWT_SECRET 环境变量，"
            "当前仍为默认值 'change-me'，JWT 可被任意伪造。"
        )

    # T3-1：废弃 Base.metadata.create_all，schema 改由 Alembic 管理。
    # 启动时用应用 engine 执行 alembic upgrade head（in-memory SQLite 也能正确迁移）。
    # 生产环境迁移失败直接 raise；dev 环境兜底用 create_all。
    from app.core.alembic_helper import ensure_schema

    ensure_schema(engine, settings.database_url, settings.env)

    with SessionLocal() as db:
        for name, code in [("本部校区", "main"), ("未来校区", "future"), ("香山校区", "xiangshan"), ("东校区", "east")]:
            if not db.scalar(select(School).where(School.code == code)):
                db.add(School(name=name, code=code))
        # 初始化徽章系统（幂等，至少 20 个种子徽章）
        _init_badges(db)
        if not db.scalar(select(Announcement)):
            db.add(Announcement(title="欢迎来到立洋社区", content="请遵守校园社区规范，友好交流，保护隐私。"))
        # 初始化 8 个圈子（与 School 初始化保持一致风格）
        _init_categories(db)
        # 初始化警告值系统默认配置（单行，id=1）
        if not db.get(WarningConfig, 1):
            db.add(WarningConfig(id=1))
        # 初始化种子邀请码（冷启动，幂等）
        _init_seed_invite_codes(db, settings.seed_invite_code_count)
        db.commit()
    logger.info("{} started (env={})", settings.app_name, settings.env)


@app.on_event("startup")
async def _start_match_cleanup() -> None:
    """启动后台清理任务：定期清理超时的匹配队列和会话。"""
    import asyncio as _asyncio
    from app.services import match_service as _ms

    async def _loop() -> None:
        while True:
            await _asyncio.sleep(10)
            try:
                with SessionLocal() as db:
                    _ms_cleanup(db)
            except Exception as exc:
                logger.warning("[MATCH_CLEANUP] err={}", exc)

    def _ms_cleanup(db) -> None:
        from datetime import timedelta
        from app.core.time_utils import now_utc
        from app.models import MatchQueue, MatchSession
        now = now_utc()
        # 1. 超时等待队列
        expired_queue = db.scalars(
            select(MatchQueue).where(
                MatchQueue.status == "waiting",
                MatchQueue.created_at < now - timedelta(seconds=_ms.WAIT_TIMEOUT_SECONDS),
            )
        ).all()
        for q in expired_queue:
            q.status = "timeout"
            _ms._fire_and_forget({
                "type": "match_timeout",
                "queue_id": q.id,
            }, q.user_id)
        # 2. 超时会话
        expired_sessions = db.scalars(
            select(MatchSession).where(
                MatchSession.status == "active",
                MatchSession.expires_at < now,
            )
        ).all()
        for s in expired_sessions:
            _ms._expire_session(db, s)
        if expired_queue or expired_sessions:
            db.commit()

    _asyncio.create_task(_loop())


def _init_categories(db) -> None:
    """初始化圈子数据（幂等，已有则跳过）。"""
    initial_circles = [
        ("校园圈", "default", None, "校园动态与日常交流", "#007aff", 0),
        ("表白墙", "confess", None, "勇敢表达你的心意", "#ff3b30", 1),
        ("失物招领", "lost", None, "丢失或捡到物品在此发布", "#ff9500", 2),
        ("二手市场", "market", None, "二手物品交易", "#34c759", 3),
        ("学习互助", "study", None, "学习资料与互助答疑", "#5856d6", 4),
        ("校园美食", "food", None, "美食探店与食堂点评", "#ff6b35", 5),
        ("游戏开黑", "game", None, "组队开黑与游戏讨论", "#af52de", 6),
        ("摄影", "photo", None, "摄影作品分享与交流", "#00c7be", 7),
        ("随机匹配", "match", None, "随机匹配陌生人聊天", "#ff9500", 8),
        ("匿名树洞", "treehole", None, "匿名倾诉心事", "#8e8e93", 9),
        ("校园问答", "qa", None, "校园问题互助问答", "#007aff", 10),
        ("跳蚤市场", "flea", None, "闲置物品跳蚤市场", "#34c759", 11),
    ]
    for name, slug, icon, description, color, sort_order in initial_circles:
        if not db.scalar(select(Category).where(Category.slug == slug)):
            db.add(
                Category(
                    name=name,
                    slug=slug,
                    icon=icon,
                    description=description,
                    color=color,
                    sort_order=sort_order,
                )
            )


def _init_seed_invite_codes(db, count: int) -> None:
    """初始化种子邀请码（幂等，已存在则补足至 count 个未使用的）。

    冷启动阶段：管理员把种子码线下发给可靠的班长/学生会主席，
    学生注册时填种子码即可直接获得 verified 状态。
    """
    import secrets
    import string
    from sqlalchemy import func

    # 查当前未使用的种子码数量（「待使用」的种子码已被管理员复制带走，不计入）
    unused = db.scalar(
        select(func.count(SeedInviteCode.id)).where(
            SeedInviteCode.used_by.is_(None),
            SeedInviteCode.status == "unused",
        )
    ) or 0
    if unused >= count:
        return  # 数量足够，跳过

    need = count - unused
    safe_chars = "".join(c for c in (string.ascii_uppercase + string.digits) if c not in "0OI1")
    for i in range(need):
        # 生成唯一码（重试 5 次）
        for _ in range(5):
            code = "S" + "".join(secrets.choice(safe_chars) for _ in range(7))  # S 前缀表示种子码
            if not db.scalar(select(SeedInviteCode).where(SeedInviteCode.code == code)):
                db.add(SeedInviteCode(code=code, note=f"启动自动生成 #{unused + i + 1}"))
                break


def _init_badges(db) -> None:
    """初始化种子徽章（幂等，已有 code 则跳过）。"""
    from app.services.badge_service import DEFAULT_BADGES

    existing_codes = set(
        db.scalars(select(Badge.code)).all()
    )
    for item in DEFAULT_BADGES:
        if item["code"] in existing_codes:
            continue
        db.add(
            Badge(
                name=item["name"],
                code=item["code"],
                icon=item["icon"],
                description=item["description"],
                sort_order=item.get("sort_order", 0),
                is_system=item.get("is_system", False),
            )
        )


app.include_router(auth.router)
app.include_router(schools.router)
app.include_router(posts.router)
app.include_router(comments.router)
app.include_router(interactions.router)
app.include_router(users.router)
app.include_router(badges.router)
app.include_router(images.router)
app.include_router(admin.router)
app.include_router(announcements.router)
app.include_router(notifications.router)
# 阶段四：圈子申请路由必须在 circles.router 之前注册，
# 否则 /circles/apply 和 /circles/my-applies 会被 /circles/{slug} 抢先匹配
app.include_router(circle_apply.router)
app.include_router(circles.router)
app.include_router(search.router)
app.include_router(follows.router)
app.include_router(messages.router)
app.include_router(checkin.router)
app.include_router(browse_history.router)
app.include_router(feedback.router)
app.include_router(deepseek.router)
app.include_router(topics.router)
app.include_router(polls.router)
app.include_router(stats.router)
app.include_router(bottles.router)
app.include_router(match.router)
app.include_router(ws.router)
app.mount("/uploads", StaticFiles(directory="uploads", check_dir=False), name="uploads")

# 前端构建产物的绝对路径（避免相对路径在不同工作目录下失效）
_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets"), check_dir=False), name="assets")


@app.get("/health")
def health() -> dict:
    return {"code": 0, "msg": "success", "data": {"status": "ok"}}


# ============ 前端 SPA 静态文件服务 ============
# 将前端构建产物（dist/）由后端直接服务，便于内网穿透/外网部署只暴露一个端口
_INDEX_HTML = _FRONTEND_DIST / "index.html"


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """SPA fallback：未匹配 API/静态文件的 GET 请求返回 index.html，由前端路由处理。"""
    # 如果请求的是 dist 中存在的具体文件（如 favicon.ico），直接返回
    candidate = _FRONTEND_DIST / full_path
    if candidate.is_file():
        return FileResponse(candidate)
    # 其余一律返回 index.html（Vue Router 接管）
    if _INDEX_HTML.exists():
        return FileResponse(_INDEX_HTML)
    raise HTTPException(status_code=404, detail="Frontend not built")
