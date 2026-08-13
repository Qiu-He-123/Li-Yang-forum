"""查看/生成微信同步客户端设备令牌。

用法（在 backend 目录）：
    .venv\\Scripts\\python scripts/init_wechat_sync.py
然后把输出的令牌填到 微信同步客户端/config.json 的 device_token。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import SessionLocal  # noqa: E402
from app.services.wechat_sync_service import get_device_token  # noqa: E402


def main() -> None:
    with SessionLocal() as db:
        token = get_device_token(db)
    print("设备令牌（填入 微信同步客户端/config.json 的 device_token）：")
    print(token)


if __name__ == "__main__":
    main()
