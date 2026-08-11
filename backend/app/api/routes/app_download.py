"""手机端 APK 下载中转。

网页端「下载手机端 → 安卓版」直接由本服务器提供 APK 文件，
不再依赖蓝奏云等第三方网盘（蓝奏云跳转会被微信拦截/提示举报）。

部署约定：把编译好的 APK 放进 backend/static/ 目录即可，
本接口自动选择目录里最新的 .apk 返回；无需改代码、无需重启
（每次请求实时读取磁盘，新包放进去立即生效）。
"""

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import extract_ip
from app.core.database import get_db
from app.models import AppDownloadLog

router = APIRouter(prefix="/api/app-download", tags=["app"])

_STATIC_DIR = Path(__file__).resolve().parent.parent.parent.parent / "static"


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


@router.get("")
def app_download(request: Request, db: Session = Depends(get_db)):
    """直接返回服务器 backend/static 里最新的 APK。"""
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
