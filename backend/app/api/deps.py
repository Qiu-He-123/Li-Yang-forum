import ipaddress
from functools import lru_cache

from fastapi import Cookie, Depends, HTTPException, Request
import jwt
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ErrorCode
from app.core.security import TOKEN_TYPE_ACCESS, TOKEN_TYPE_ADMIN, decode_token
from app.core.time_utils import now_utc
from app.core.config import get_settings
from app.models import Admin, User


@lru_cache(maxsize=1)
def _trusted_proxy_networks() -> list:
    """解析可信反代白名单（IP/CIDR）。"""
    raw = get_settings().trusted_proxies or ""
    networks = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            continue
    return networks


def _is_trusted_proxy(peer_ip: str | None) -> bool:
    """当前直连来源是否为可信反代（Nginx）。"""
    if not peer_ip:
        return False
    try:
        ip = ipaddress.ip_address(peer_ip)
    except ValueError:
        return False
    return any(ip in net for net in _trusted_proxy_networks())


def extract_ip(request: Request | None = None) -> str | None:
    """从 Request 中提取客户端真实 IP。

    安全设计（防 X-Forwarded-For 伪造绕过限流）：
    - 仅当直连来源是可信反代（trusted_proxies 白名单，默认 docker/本机网段）
      且生产模式时才信任 X-Real-IP；后端端口被直接暴露时伪造头无效
    - dev 直跑 uvicorn 时一律用 TCP 对端 IP（request.client.host），
      客户端伪造 X-Real-IP / X-Forwarded-For 均无效
    - 仍无效返回 None
    """
    if request is None:
        return None
    settings = get_settings()
    peer = request.client.host if request.client else None
    if settings.env != "dev" and _is_trusted_proxy(peer):
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            ip = real_ip.strip()
            try:
                ipaddress.ip_address(ip)
                return ip
            except ValueError:
                # X-Real-IP 非法（理论上只有我们自己的 Nginx 会设置），fallback
                pass
    return peer


def _resolve_user(access_token: str | None, refresh_token: str | None, db: Session) -> User:
    """内部：从 Cookie 解析用户，未登录或无效 token 抛对应错误。"""
    if not access_token:
        if refresh_token:
            raise HTTPException(status_code=401, detail=ErrorCode.TOKEN_INVALID)
        raise HTTPException(status_code=401, detail=ErrorCode.NOT_LOGGED_IN)
    try:
        user_id = int(decode_token(access_token, TOKEN_TYPE_ACCESS))
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(status_code=401, detail=ErrorCode.TOKEN_INVALID) from None
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail=ErrorCode.USER_NOT_FOUND)
    return user


def _is_user_banned(user: User) -> bool:
    """判断用户是否处于封禁状态（无副作用，不修改 user 对象）。

    - ban_until 不为空且未过期 → 临时封禁
    - ban_until 为空且 is_active 为 False → 永久封禁
    """
    if user.ban_until:
        return user.ban_until > now_utc()
    return not user.is_active


def current_user(
    access_token: str | None = Cookie(default=None),
    refresh_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not access_token:
        # access_token 缺失（通常因 max_age 过期被浏览器清除），
        # 但 refresh_token 仍在 → 返回 TOKEN_INVALID(-101) 触发前端自动 refresh，
        # 避免用户 30 分钟空闲后被强制登出。
        if refresh_token:
            raise HTTPException(status_code=401, detail=ErrorCode.TOKEN_INVALID)
        raise HTTPException(status_code=401, detail=ErrorCode.NOT_LOGGED_IN)
    try:
        user_id = int(decode_token(access_token, TOKEN_TYPE_ACCESS))
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(status_code=401, detail=ErrorCode.TOKEN_INVALID) from None
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail=ErrorCode.USER_NOT_FOUND)
    # 封号用户：直接拦截所有非豁免接口，返回 -301 让前端跳转封号提示页。
    # 豁免接口（登录/登出/会话校验/封号状态/申诉）使用 current_user_allow_banned。
    if _is_user_banned(user):
        raise HTTPException(status_code=403, detail=ErrorCode.USER_BANNED)
    return user


def current_user_allow_banned(
    access_token: str | None = Cookie(default=None),
    refresh_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    """与 current_user 相同，但不拦截封号用户。

    仅供需要让封号用户访问的接口使用：/auth/me（会话校验+返回 ban_info）、
    /auth/logout（封号页退出登录）、/users/me/ban-status（查看封号信息）、
    /users/me/appeals（提交/查看申诉）。
    """
    if not access_token:
        if refresh_token:
            raise HTTPException(status_code=401, detail=ErrorCode.TOKEN_INVALID)
        raise HTTPException(status_code=401, detail=ErrorCode.NOT_LOGGED_IN)
    try:
        user_id = int(decode_token(access_token, TOKEN_TYPE_ACCESS))
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(status_code=401, detail=ErrorCode.TOKEN_INVALID) from None
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail=ErrorCode.USER_NOT_FOUND)
    return user


def current_user_optional(
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User | None:
    """可选登录：未登录返回 None，登录后返回用户。

    与 optional_user 行为一致：封号用户一律拦截（403），防止封号用户
    通过内容浏览接口继续访问。
    """
    if not access_token:
        return None
    try:
        user_id = int(decode_token(access_token, TOKEN_TYPE_ACCESS))
    except (jwt.InvalidTokenError, ValueError):
        return None
    user = db.get(User, user_id)
    if not user:
        return None
    if _is_user_banned(user):
        raise HTTPException(status_code=403, detail=ErrorCode.USER_BANNED)
    return user


def optional_user(access_token: str | None = Cookie(default=None), db: Session = Depends(get_db)) -> User | None:
    """可选用户：有有效 token 返回 User，否则返回 None（匿名访问）。

    用于首页/圈子页等公开浏览接口，未登录用户可看公开帖子，
    登录用户额外能看到自己的私密帖子和按学校筛选。
    封号用户同样被拦截（返回 -301），避免封号用户浏览内容。
    """
    if not access_token:
        return None
    try:
        user_id = int(decode_token(access_token, TOKEN_TYPE_ACCESS))
    except (jwt.InvalidTokenError, ValueError):
        return None
    user = db.get(User, user_id)
    if not user:
        return None
    # 封号用户：即使是在公开浏览接口也拦截
    if _is_user_banned(user):
        raise HTTPException(status_code=403, detail=ErrorCode.USER_BANNED)
    return user


def admin_user(admin_token: str | None = Cookie(default=None, alias="admin_token"), db: Session = Depends(get_db)) -> Admin:
    """校验管理员 Cookie 并返回 Admin 实例。

    与用户 access_token 区分独立 admin_token Cookie，避免越权。
    失败抛 401 NOT_LOGGED_IN / TOKEN_INVALID / USER_NOT_FOUND。
    """
    if not admin_token:
        raise HTTPException(status_code=401, detail=ErrorCode.NOT_LOGGED_IN)
    try:
        admin_id = int(decode_token(admin_token, TOKEN_TYPE_ADMIN))
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(status_code=401, detail=ErrorCode.TOKEN_INVALID) from None
    admin = db.get(Admin, admin_id)
    if not admin:
        raise HTTPException(status_code=401, detail=ErrorCode.USER_NOT_FOUND)
    return admin


def verified_user(
    access_token: str | None = Cookie(default=None),
    refresh_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> User:
    """已认证用户依赖（邀请码系统三状态）。

    比 current_user 更严格：
    - 未登录 → 401 NOT_LOGGED_IN
    - 封号用户 → 403 USER_BANNED
    - 已注册但未填邀请码（verification_status=unverified）→ 403 INVITE_CODE_REQUIRED

    用于发帖 / 评论 / 随机匹配 / 漂流瓶等需要解锁的功能。
    """
    user = _resolve_user(access_token, refresh_token, db)
    if _is_user_banned(user):
        raise HTTPException(status_code=403, detail=ErrorCode.USER_BANNED)
    if user.verification_status != "verified":
        raise HTTPException(status_code=403, detail=ErrorCode.INVITE_CODE_REQUIRED)
    return user
