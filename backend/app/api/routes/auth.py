from fastapi import APIRouter, Cookie, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import current_user, current_user_allow_banned
from app.core.database import get_db
from app.models import User
from app.schemas.auth import (
    ChangePasswordIn,
    InviteCodeApplyIn,
    LoginIn,
    RegisterIn,
    UpdateQQIn,
)
from app.schemas.common import ok
from app.services import auth_service, user_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register")
def register(payload: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    """注册：用户名 + 密码 + 校区 + 协议；QQ 与邀请码均选填。

    - 注册时填邀请码 → 直接 verified
    - 注册时填种子码 → 直接 verified（消耗一个种子码）
    - 都不填 → unverified，可后续通过 /auth/apply-invite-code 补填
    """
    data = auth_service.register(payload, request, response, db)
    return ok(data)


@router.post("/login")
def login(payload: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    """登录：用户名 + 密码。"""
    data = auth_service.login(payload, request, response, db)
    return ok(data)


@router.post("/logout")
def logout(response: Response, db: Session = Depends(get_db), user: User = Depends(current_user_allow_banned)) -> dict:
    """登出：清 Cookie + 撤销 refresh_token。封号用户也可登出。"""
    auth_service.logout(response, db, user)
    return ok()


@router.post("/refresh")
def refresh(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """用 refresh_token 换新 access_token。

    无需 current_user 依赖；refresh_token 通过 Cookie 传入。
    失败返回 401 TOKEN_INVALID，前端清 session 跳登录。
    """
    data = auth_service.refresh_session(refresh_token, request, response, db)
    return ok(data)


@router.get("/me")
def auth_me(db: Session = Depends(get_db), user: User = Depends(current_user_allow_banned)) -> dict:
    """校验当前会话是否有效。前端刷新页面后调用此接口确认登录态。

    使用 current_user_allow_banned：封号用户也能通过认证，
    返回 ban_info 让前端 validateSession 检测封禁并跳转封号提示页。
    新增 verification_status 字段，前端用于判断是否需要弹邀请码提示。
    """
    ban_status = user_service.get_ban_status(user, db)
    return ok({
        "user_id": user.id,
        "nickname": user.nickname,
        "school_id": user.school_id,
        "username": user.username,
        "verification_status": user.verification_status,
        "ban_info": ban_status if ban_status["is_banned"] else None,
    })


@router.post("/change-password")
def change_password(
    payload: ChangePasswordIn,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """修改密码：校验旧密码 → 更新密码哈希 → 重发 token。"""
    return ok(auth_service.change_password(payload, request, response, db, user))


# ============ 邀请码系统 ============

@router.post("/apply-invite-code")
def apply_invite_code(
    payload: InviteCodeApplyIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """填写邀请码解锁全部功能（已注册用户补填邀请码）。

    支持两种邀请码：
    - 其他 verified 用户的邀请码（受 3 天冷却 + 连坐冻结约束）
    - 管理员预生成的种子码（一次性，无邀请人）
    """
    return ok(auth_service.apply_invite_code(payload, request, db, user))


@router.get("/invite-code")
def get_my_invite_code(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """获取自己的邀请码 + 分享状态（3 天冷却 + 连坐冻结）。"""
    return ok(auth_service.get_my_invite_code(db, user))


@router.get("/verification-status")
def get_verification_status(
    user: User = Depends(current_user),
) -> dict:
    """查询当前用户的认证状态（unverified / verified）。"""
    return ok(auth_service.get_verification_status(user))


@router.patch("/qq")
def update_qq(
    payload: UpdateQQIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    """修改 QQ 号（设置页，仅用于找回账号）。"""
    return ok(auth_service.update_qq(payload, request, db, user))
