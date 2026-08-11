"""头像 URL 统一处理：无头像的用户返回系统默认头像，避免列表满屏字母占位。"""

from urllib.parse import urlparse

DEFAULT_AVATAR = "/default-avatar.svg"


def avatar_url_or_default(url: str | None) -> str:
    """返回可展示的头像 URL。

    - 空头像 → 系统默认头像（/default-avatar.svg，随前端 dist 提供）
    - 历史数据里存了带域名的绝对地址 → 统一转成相对路径（兼容换域名/换端口）
    """
    if not url or not url.strip():
        return DEFAULT_AVATAR
    url = url.strip()
    if url.startswith(("http://", "https://")):
        parsed = urlparse(url)
        path = parsed.path or ""
        if path.startswith(("/uploads/", "/minio/", "/images/")):
            return path
    return url
