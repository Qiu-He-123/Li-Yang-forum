from pydantic import BaseModel, Field, field_validator


class RegisterIn(BaseModel):
    """注册入参（邀请码系统三状态）。

    新方案：用户名 + 密码 + 校区 + 协议；QQ 与邀请码均为选填。
    - QQ 选填：仅用于找回账号，可在设置中随时修改
    - 邀请码 选填：注册时填了邀请码直接 verified；不填则 unverified，可后续补填
    """
    nickname: str = Field(min_length=1, max_length=32)
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=72)
    confirm_password: str = Field(min_length=8, max_length=72)
    school_id: int
    agreed: bool
    qq: str | None = Field(default=None, max_length=20)
    invite_code: str | None = Field(default=None, max_length=16)

    @field_validator("username")
    @classmethod
    def username_format(cls, v: str) -> str:
        """用户名仅允许字母/数字/下划线，3-32 字符。"""
        if not v or not all(c.isalnum() or c == "_" for c in v):
            raise ValueError("用户名只能包含字母、数字和下划线")
        return v


class LoginIn(BaseModel):
    """登录入参：用户名 + 密码（不再支持验证码登录，简化方案）。"""

    username: str
    password: str


class AdminLoginIn(BaseModel):
    """管理员登录入参。

    用 Pydantic Body 而非 URL query，避免密码出现在访问日志/浏览器历史（S3）。
    """

    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=72)


class RefreshIn(BaseModel):
    """refresh_token 通常从 Cookie 读取，但保留 schema 用于文档与测试。"""

    refresh_token: str | None = None


class ChangePasswordIn(BaseModel):
    """修改密码入参（T5-2）。"""

    old_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=8, max_length=72)
    confirm_password: str = Field(min_length=8, max_length=72)


class InviteCodeApplyIn(BaseModel):
    """填写邀请码解锁功能入参。"""

    code: str = Field(min_length=4, max_length=16)


class UpdateQQIn(BaseModel):
    """修改 QQ 号入参（设置页）。"""

    qq: str | None = Field(default=None, max_length=20)
