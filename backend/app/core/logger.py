"""日志配置模块。

启动时调用 setup_logger() 即可同时输出到控制台和 logs/app.log 文件，
按大小滚动，方便排查用户操作错误。
"""

import sys
from pathlib import Path

from loguru import logger


def setup_logger(log_dir: str = "logs") -> None:
    """配置 loguru：控制台彩色输出 + 文件滚动日志。"""
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logger.add(
        Path(log_dir) / "app.log",
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{line} - {message}",
    )
