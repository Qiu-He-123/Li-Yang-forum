"""统一错误码与错误消息映射。

所有业务错误统一返回错误码（int），由 get_error_message(code) 翻译为具体中文消息。
前端只需要识别 code 即可决定 UI 行为，msg 用于直接展示给用户。
"""

from typing import Any


class ErrorCode:
    """错误码常量。负数表示业务错误，正数保留给 HTTP 状态码兼容。"""

    # ============ 参数校验类 ============
    PHONE_MISSING = -1
    PHONE_INVALID = -2
    PASSWORD_MISSING = -3
    PASSWORD_TOO_SHORT = -4
    CODE_MISSING = -5
    CODE_INVALID = -6
    SCHOOL_MISSING = -7
    NICKNAME_MISSING = -8
    CONTENT_EMPTY = -9
    CONTENT_TOO_LONG = -10
    IMAGES_TOO_MANY = -11
    CONFIRM_PASSWORD_MISSING = -12
    AGREED_NOT_CHECKED = -13
    REASON_EMPTY = -14
    TARGET_TYPE_INVALID = -15

    # ============ 鉴权类 ============
    NOT_LOGGED_IN = -100
    TOKEN_INVALID = -101
    USER_NOT_FOUND = -102
    LOGIN_FAILED = -103
    LOGIN_LOCKED = -104

    # ============ 业务冲突类 ============
    NOT_AGREED = -200
    PASSWORD_MISMATCH = -201
    PHONE_REGISTERED = -202
    SCHOOL_NOT_FOUND = -203
    CATEGORY_NOT_FOUND = -204
    POST_NOT_FOUND = -205
    COMMENT_NOT_FOUND = -206
    TARGET_NOT_FOUND = -207
    REPORT_TARGET_NOT_FOUND = -208
    INVALID_LIKE_TARGET = -209
    PARENT_COMMENT_NOT_FOUND = -210
    POST_PRIVATE = -211        # 帖子为私密发布，仅作者可见
    BADGE_NOT_FOUND = -212     # 徽章不存在或已停用
    BADGE_CODE_INVALID = -213  # 激活码无效或已被使用
    BADGE_ALREADY_OWNED = -214 # 已拥有该徽章
    BADGE_CANNOT_WEAR = -215   # 未拥有该徽章，无法佩戴

    # ============ 权限类 ============
    NO_PERMISSION = -300
    USER_BANNED = -301
    # 邀请码系统（三状态：guest/unverified/verified）
    INVITE_CODE_REQUIRED = -302  # 已注册但未填邀请码，需要解锁
    INVITE_CODE_INVALID = -303   # 邀请码不存在或已被使用
    INVITE_CODE_COOLDOWN = -304  # 自己的邀请码 3 天冷却中
    INVITE_PRIVILEGE_FROZEN = -305  # 因连坐被冻结分享资格
    USERNAME_EXISTS = -306       # 用户名已被注册

    # ============ 兜底 ============
    PARAM_ERROR = -1000
    UNKNOWN_ERROR = -9999


_ERROR_MESSAGES: dict[int, str] = {
    ErrorCode.PHONE_MISSING: "手机号未填写",
    ErrorCode.PHONE_INVALID: "手机号格式错误",
    ErrorCode.PASSWORD_MISSING: "密码未填写",
    ErrorCode.PASSWORD_TOO_SHORT: "密码长度不能少于8位",
    ErrorCode.CODE_MISSING: "验证码未填写",
    ErrorCode.CODE_INVALID: "验证码错误",
    ErrorCode.SCHOOL_MISSING: "校区未选择",
    ErrorCode.NICKNAME_MISSING: "昵称未填写",
    ErrorCode.CONTENT_EMPTY: "内容不能为空",
    ErrorCode.CONTENT_TOO_LONG: "内容超过最大长度限制",
    ErrorCode.IMAGES_TOO_MANY: "图片最多9张",
    ErrorCode.CONFIRM_PASSWORD_MISSING: "确认密码未填写",
    ErrorCode.AGREED_NOT_CHECKED: "请先阅读并同意协议",
    ErrorCode.REASON_EMPTY: "举报理由不能为空",
    ErrorCode.TARGET_TYPE_INVALID: "目标类型无效",
    ErrorCode.NOT_LOGGED_IN: "未登录，请先登录",
    ErrorCode.TOKEN_INVALID: "登录已过期，请重新登录",
    ErrorCode.USER_NOT_FOUND: "用户不存在",
    ErrorCode.LOGIN_FAILED: "账号或密码错误，请使用注册时的账号登录（不是昵称）",
    ErrorCode.LOGIN_LOCKED: "连续登录失败过多，请 30 分钟后再试",
    ErrorCode.NOT_AGREED: "请先阅读并同意协议",
    ErrorCode.PASSWORD_MISMATCH: "两次密码不一致",
    ErrorCode.PHONE_REGISTERED: "手机号已注册",
    ErrorCode.SCHOOL_NOT_FOUND: "校区不存在",
    ErrorCode.CATEGORY_NOT_FOUND: "分类不存在",
    ErrorCode.POST_NOT_FOUND: "帖子不存在或已被删除",
    ErrorCode.POST_PRIVATE: "该帖子为私密发布，仅作者可见",
    ErrorCode.BADGE_NOT_FOUND: "徽章不存在或已停用",
    ErrorCode.BADGE_CODE_INVALID: "激活码无效或已被使用",
    ErrorCode.BADGE_ALREADY_OWNED: "您已拥有该徽章",
    ErrorCode.BADGE_CANNOT_WEAR: "您还未获得该徽章，无法佩戴",
    ErrorCode.COMMENT_NOT_FOUND: "评论不存在",
    ErrorCode.TARGET_NOT_FOUND: "对象不存在",
    ErrorCode.REPORT_TARGET_NOT_FOUND: "举报对象不存在",
    ErrorCode.INVALID_LIKE_TARGET: "点赞对象无效",
    ErrorCode.PARENT_COMMENT_NOT_FOUND: "父评论不存在",
    ErrorCode.NO_PERMISSION: "无权限操作",
    ErrorCode.USER_BANNED: "账号已被封禁，无法操作",
    ErrorCode.INVITE_CODE_REQUIRED: "需要邀请码才能使用此功能",
    ErrorCode.INVITE_CODE_INVALID: "邀请码无效或已被使用",
    ErrorCode.INVITE_CODE_COOLDOWN: "邀请码分享冷却中，3 天仅可分享一次",
    ErrorCode.INVITE_PRIVILEGE_FROZEN: "邀请资格已被冻结（被邀请人违规连坐）",
    ErrorCode.USERNAME_EXISTS: "账号已被注册，请换个账号试试",
    ErrorCode.PARAM_ERROR: "参数错误",
    ErrorCode.UNKNOWN_ERROR: "未知错误",
}


def get_error_message(code: int) -> str:
    """根据错误码返回具体的中文错误原因。"""
    return _ERROR_MESSAGES.get(code, "未知错误")


def error_response(code: int, data: Any = None) -> dict[str, Any]:
    """生成统一错误返回结构。"""
    return {"code": code, "msg": get_error_message(code), "data": data or {}}


def pydantic_error_to_code(errors: list[dict]) -> int:
    """将 pydantic 校验错误列表中的第一条映射为业务错误码。

    通过 loc 的最后一段定位字段名，结合 type 判断缺失/格式/长度等具体原因。
    """
    if not errors:
        return ErrorCode.PARAM_ERROR
    err = errors[0]
    loc = err.get("loc", [])
    field = loc[-1] if loc else ""
    err_type = err.get("type", "")

    is_missing = "missing" in err_type
    is_min_length = "min_length" in err_type
    is_max_length = "max_length" in err_type
    is_too_short = "too_short" in err_type or is_min_length
    is_too_long = "too_long" in err_type or is_max_length

    field_map = {
        "phone": (ErrorCode.PHONE_MISSING, ErrorCode.PHONE_INVALID, ErrorCode.PHONE_INVALID),
        "password": (ErrorCode.PASSWORD_MISSING, ErrorCode.PASSWORD_TOO_SHORT, ErrorCode.PASSWORD_MISSING),
        "confirm_password": (ErrorCode.CONFIRM_PASSWORD_MISSING, ErrorCode.PASSWORD_TOO_SHORT, ErrorCode.CONFIRM_PASSWORD_MISSING),
        "code": (ErrorCode.CODE_MISSING, ErrorCode.CODE_INVALID, ErrorCode.CODE_INVALID),
        "school_id": (ErrorCode.SCHOOL_MISSING, ErrorCode.SCHOOL_MISSING, ErrorCode.SCHOOL_MISSING),
        "nickname": (ErrorCode.NICKNAME_MISSING, ErrorCode.NICKNAME_MISSING, ErrorCode.NICKNAME_MISSING),
        "content": (ErrorCode.CONTENT_EMPTY, ErrorCode.CONTENT_EMPTY, ErrorCode.CONTENT_TOO_LONG),
        "image_urls": (ErrorCode.IMAGES_TOO_MANY, ErrorCode.IMAGES_TOO_MANY, ErrorCode.IMAGES_TOO_MANY),
        "reason": (ErrorCode.REASON_EMPTY, ErrorCode.REASON_EMPTY, ErrorCode.REASON_EMPTY),
        "target_type": (ErrorCode.TARGET_TYPE_INVALID, ErrorCode.TARGET_TYPE_INVALID, ErrorCode.TARGET_TYPE_INVALID),
        "agreed": (ErrorCode.AGREED_NOT_CHECKED, ErrorCode.AGREED_NOT_CHECKED, ErrorCode.AGREED_NOT_CHECKED),
    }

    # value_error 一般是自定义校验器抛出（如图片 URL 协议非法），统一返回 PARAM_ERROR
    # 并由后端在 errors 中带具体 msg 描述，前端可直接展示 msg。
    if err_type == "value_error":
        return ErrorCode.PARAM_ERROR

    if field in field_map:
        missing_code, short_code, long_code = field_map[field]
        if is_missing:
            return missing_code
        if is_too_short:
            return short_code
        if is_too_long:
            return long_code
        return short_code

    return ErrorCode.PARAM_ERROR
