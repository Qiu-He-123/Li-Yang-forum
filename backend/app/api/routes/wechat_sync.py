"""微信朋友圈同步接口。

用户侧（/api/wechat/*）：
- POST /bind                 绑定（输入微信号/wxid）
- GET  /status               绑定状态 + 金币 + 新手引导标记
- PATCH /sync-config         自动同步开关
- GET  /moments              我的朋友圈列表（手动导入候选）
- POST /import               手动导入（可选置顶，按天收费）
- POST /refresh              立即刷新（触发同步客户端马上扫描）
- GET  /feed                 微信朋友圈频道 feed

设备侧（/api/wechat-sync/*，X-Device-Token 鉴权）：
- POST /friends              上报好友快照
- POST /ingest               上报单条朋友圈（multipart，文件字段名统一为 files）
- GET  /ping                 心跳 + 领取"立即刷新"指令
"""

import asyncio
import io
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import current_user, optional_user, verified_user
from app.core.database import get_db
from app.models import User
from app.schemas.common import ok
from app.services import wechat_sync_service

router = APIRouter(prefix="/wechat", tags=["wechat"])
device_router = APIRouter(prefix="/wechat-sync", tags=["wechat-sync"])


def require_device_token(request: Request, db: Session = Depends(get_db)) -> None:
    token = request.headers.get("x-device-token", "")
    if not token or token != wechat_sync_service.get_device_token(db):
        raise HTTPException(status_code=401, detail="设备令牌无效")


# ============ 用户侧 ============

@router.get("/bind-guide")
def bind_guide(
    db: Session = Depends(get_db),
    user: User = Depends(verified_user),
) -> dict:
    """需要添加的社区微信号（后台可改）。"""
    return ok(wechat_sync_service.get_bind_guide(db))


@router.post("/bind")
async def bind_wechat(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(verified_user),
) -> dict:
    """分步绑定第 1 步：查好友 + 生成消息验证码。
    好友不存在时先让客户端重新上报好友快照，等 1 秒再查一次。
    """
    query = (payload.get("query") or payload.get("wxid") or payload.get("wechat_id") or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="请输入微信号或 wxid")
    binding = wechat_sync_service.start_bind(db, user, query)
    if binding is None:
        # 可能好友刚加、快照还没刷新：通知客户端重传，等 1 秒再查（异步等待，不卡请求线程）
        wechat_sync_service.request_friend_refresh(db)
        await asyncio.sleep(1)
        binding = wechat_sync_service.start_bind(db, user, query)
    if binding is None:
        raise HTTPException(
            status_code=404,
            detail="未找到该微信好友，请确认已添加社区微信后重试",
        )
    guide = wechat_sync_service.get_bind_guide(db)
    return ok(
        {
            "step": "code",
            "verify_code": binding.verify_code,
            "wechat_id": guide.get("wechat_id") or "",
            "wxid": binding.wxid,
            "nickname": binding.nickname,
        }
    )


@router.post("/bind/verify-code")
async def verify_bind_code(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(verified_user),
) -> dict:
    """分步绑定第 2 步：校验用户是否真的把验证码发给了社区微信号。"""
    code = payload.get("code") or ""
    # 实时校验要做微信数据库解密（同步、较慢），丢线程池避免阻塞事件循环
    result = await asyncio.to_thread(wechat_sync_service.verify_bind_code, db, user, code)
    if not result.get("matched"):
        # 客户端上报消息有延迟，等 1 秒再看一次
        await asyncio.sleep(1)
        result = await asyncio.to_thread(wechat_sync_service.verify_bind_code, db, user, code)
    return ok(result)


@router.get("/status")
def get_status(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    return ok(wechat_sync_service.binding_status(db, user))


@router.patch("/sync-config")
def update_sync_config(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    return ok(wechat_sync_service.set_sync_enabled(db, user, bool(payload.get("enabled"))))


@router.get("/moments")
def list_moments(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    return ok(wechat_sync_service.list_my_moments(db, user, page, page_size))


@router.post("/import")
def import_moments(
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    tids = payload.get("tids") or []
    pinned_tids = payload.get("pinned_tids") or []
    pin_days = int(payload.get("pin_days") or 1)
    result = wechat_sync_service.import_moments(db, user, tids, pinned_tids, pin_days)
    return ok(result)


@router.post("/refresh")
def refresh_moments(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """立即刷新：后端当场直读本地微信数据库并入库，返回新增数量。"""
    result = wechat_sync_service.refresh_moments(db, user)
    return ok({"refreshing": True, **result})


@router.post("/unbind")
def unbind_wechat(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """用户自助解绑：解除当前绑定，随后可重新绑定其他微信号。"""
    return ok(wechat_sync_service.unbind_wechat(db, user))


@router.get("/feed")
def moments_feed(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> dict:
    return ok(wechat_sync_service.moments_feed(db, user, page, page_size))


@router.get("/thumb")
def moment_thumb(url: str = Query(..., description="朋友圈媒体 URL（/uploads/wechat/xxx.jpg）")) -> Response:
    """朋友圈图片压缩缩略图：限制最长边 + JPEG 压缩，大幅减小加载体积。
    仅允许读取 uploads 目录下的图片；视频等非图片类型返回 404。
    """
    if not url or not url.startswith("/uploads/"):
        raise HTTPException(status_code=400, detail="无效的图片地址")
    path = Path(url.lstrip("/"))
    # 防止目录穿越：解析后必须仍在 uploads 目录内
    try:
        resolved = path.resolve()
        resolved.relative_to(Path("uploads").resolve())
    except (ValueError, OSError):
        raise HTTPException(status_code=400, detail="无效的图片地址") from None
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="图片不存在")
    try:
        from PIL import Image

        with Image.open(str(resolved)) as im:
            im = im.convert("RGB") if im.mode not in ("RGB", "L") else im
            # 最长边不超过 800px（微信原图通常 1080+）
            max_side = 800
            w, h = im.size
            if max(w, h) > max_side:
                ratio = max_side / max(w, h)
                im = im.resize((max(1, int(w * ratio)), max(1, int(h * ratio))), Image.LANCZOS)
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=70, optimize=True)
    except Exception:
        raise HTTPException(status_code=404, detail="图片处理失败") from None
    return Response(
        content=buf.getvalue(),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


# ============ 设备侧 ============

@device_router.post("/friends")
def upload_friends(
    payload: dict,
    db: Session = Depends(get_db),
    _: None = Depends(require_device_token),
) -> dict:
    added = wechat_sync_service.upsert_friends(db, payload.get("friends") or [])
    return ok({"added": added})


@device_router.post("/ingest")
async def ingest_moment(
    tid: str = Form(...),
    wxid: str = Form(""),
    author_name: str = Form(""),
    content: str = Form(""),
    create_time: int = Form(0),
    files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
    _: None = Depends(require_device_token),
) -> dict:
    media_files = []
    for f in files or []:
        raw = await f.read()
        # 朋友圈媒体类型：2=图片 6=视频 5=音乐 3/4=视频
        media_files.append((2, raw))
    result = await wechat_sync_service.ingest_moment(
        db,
        {
            "tid": tid,
            "wxid": wxid,
            "author_name": author_name,
            "content": content,
            "create_time": create_time,
        },
        media_files,
    )
    return ok(result)


@device_router.get("/ping")
def ping(
    db: Session = Depends(get_db),
    _: None = Depends(require_device_token),
) -> dict:
    return ok(
        {
            "force_wxid": wechat_sync_service.consume_force_refresh(db),
            "force_friends": wechat_sync_service.consume_friend_refresh(db),
            "report_messages": wechat_sync_service.has_pending_bindings(db),
            # 自动同步账号及分界线随心跳一起下发，客户端不用再单独请求 /cutoffs
            "cutoffs": wechat_sync_service.get_auto_sync_cutoffs(db),
            "server_time": __import__("datetime").datetime.now().isoformat(),
        }
    )


@device_router.get("/cutoffs")
def auto_sync_cutoffs(
    db: Session = Depends(get_db),
    _: None = Depends(require_device_token),
) -> dict:
    return ok({"items": wechat_sync_service.get_auto_sync_cutoffs(db)})


@device_router.post("/messages/recent")
def report_recent_messages(
    payload: dict,
    db: Session = Depends(get_db),
    _: None = Depends(require_device_token),
) -> dict:
    """客户端上报社区账号收到的最近消息（绑定验证码校验用）。"""
    updated = wechat_sync_service.report_recent_messages(db, payload.get("items") or [])
    return ok({"updated": updated})
