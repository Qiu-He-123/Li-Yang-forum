"""手机端 APK 下载中转（防刷下载 / 防带宽被打满）。

流程：
1. 前端弹验证码，用户通过后 POST /api/app-download/token 换取一次性下载令牌
2. 浏览器跳转 GET /api/app-download?token=xxx 下载

防护：
- 图形验证码：下载前必须通过（一次性、2 分钟过期、绑定 IP）
- 应用层限流：每 IP 每小时最多 5 次、每天最多 20 次
- Nginx 层：独立限频（6 次/分）+ 限速（512KB/s）+ 限并发（同 IP 2 连接）

部署约定：把编译好的 APK 放进 backend/static/ 目录即可，
本接口自动选择目录里最新的 .apk 返回；无需改代码、无需重启
（每次请求实时读取磁盘，新包放进去立即生效）。
"""

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import extract_ip
from app.core.database import get_db
from app.core.errors import ErrorCode
from app.models import AppDownloadLog
from app.schemas.common import ok
from app.services.captcha_service import (
    consume_download_token,
    issue_download_token as create_download_token,
    verify_captcha,
)
from app.services.rate_limit_service import check_rate_limit

router = APIRouter(prefix="/api/app-download", tags=["app"])

_STATIC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "static"

# 下载限流：每 IP 每小时最多 5 次、每天最多 20 次
DL_HOURLY_LIMIT = 5
DL_DAILY_LIMIT = 20


class DownloadTokenIn(BaseModel):
    captcha_id: str | None = Field(default=None, min_length=1, max_length=64)
    captcha_text: str | None = Field(default=None, min_length=1, max_length=16)


def _find_apk() -> Path | None:
    """返回 backend/static 目录中最新的 .apk 文件。"""
    try:
        candidates = [p for p in _STATIC_DIR.glob("*.apk") if p.is_file()]
    except OSError:
        return None
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _record_download(request: Request, db: Session) -> None:
    """记录一次下载（IP / UA），供后台数据看板统计。"""
    db.add(
        AppDownloadLog(
            ip=extract_ip(request),
            user_agent=(request.headers.get("user-agent") or "")[:255],
        )
    )
    db.commit()


def issue_download_token(request: Request, payload: DownloadTokenIn, db: Session = Depends(get_db)) -> dict:
    """验证码通过后签发一次性下载令牌。"""
    ip = extract_ip(request)
    verify_captcha(db, payload.captcha_id, payload.captcha_text, ip)
    token = create_download_token(db, ip)
    return ok({"download_token": token, "expires_in": 120})


@router.get("")
def app_download(request: Request, db: Session = Depends(get_db)):
    """验证码放行后返回服务器 backend/static 里最新的 APK。"""
    ip = extract_ip(request)
    safe_ip = ip or "unknown"

    # 1. 应用层限流：每 IP 每小时最多 5 次、每天最多 20 次
    if not check_rate_limit(db, f"dl:{safe_ip}:hour", DL_HOURLY_LIMIT, window_seconds=3600):
        return JSONResponse(
            status_code=200,
            content={"code": ErrorCode.RATE_LIMITED, "msg": "下载太频繁，请稍后再试", "data": {}},
        )
    if not check_rate_limit(db, f"dl:{safe_ip}:day", DL_DAILY_LIMIT, window_seconds=86400):
        return JSONResponse(
            status_code=200,
            content={"code": ErrorCode.RATE_LIMITED, "msg": "今日下载次数已达上限，请明天再试", "data": {}},
        )

    # 2. 下载令牌校验：必须先过验证码（一次性、2 分钟、绑定 IP）
    token = request.query_params.get("token")
    if not consume_download_token(db, token, ip):
        return JSONResponse(
            status_code=200,
            content={"code": ErrorCode.CAPTCHA_REQUIRED, "msg": "请先完成验证码验证后下载", "data": {}},
        )

    apk = _find_apk()
    if not apk:
        return JSONResponse(
            status_code=404,
            content={"code": 404, "msg": "安装包暂未上传", "data": None},
        )
    _record_download(request, db)
    return FileResponse(
        apk,
        media_type="application/vnd.android.package-archive",
        filename=apk.name,
        # 禁止浏览器缓存：每次点击都拿服务器上的最新 APK，避免下到旧包
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
