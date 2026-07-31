import asyncio
from io import BytesIO
from pathlib import Path

import aiofiles
from loguru import logger

from app.core.config import get_settings

# T8-1：缓存 MinIO 不可用状态，避免每次上传都尝试连接（每次超时 30 秒）
_minio_checked: bool = False
_minio_available: bool = False


class StorageService:
    def _check_minio(self) -> bool:
        """检查 MinIO 是否可用，结果缓存避免重复连接。"""
        global _minio_checked, _minio_available
        if _minio_checked:
            return _minio_available

        settings = get_settings()
        try:
            from minio import Minio

            client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
            )
            # 用短超时检查 bucket 是否存在（3秒超时，避免长时间阻塞）
            import signal

            # MinIO SDK 不直接支持超时参数，使用线程 + 超时控制
            def _check():
                client.bucket_exists(settings.minio_bucket)

            thread = __import__("threading").Thread(target=_check, daemon=True)
            thread.start()
            thread.join(timeout=3)
            if thread.is_alive():
                raise TimeoutError("MinIO bucket check timed out")

            _minio_available = True
        except Exception as exc:
            logger.warning("MinIO 不可用，本次会话将使用本地存储: {}", type(exc).__name__)
            _minio_available = False
        finally:
            _minio_checked = True
        return _minio_available

    async def upload_image_async(self, filename: str, content: bytes, content_type: str) -> str:
        """异步上传图片：本地存储使用 aiofiles 避免阻塞事件循环。

        性能优化：
        - 本地存储使用 aiofiles 异步写入（非阻塞）
        - MinIO 上传使用 run_in_executor 放到线程池（避免阻塞事件循环）
        - MinIO 连接检查已有缓存 + 超时保护
        """
        settings = get_settings()

        # T8-1：如果 MinIO 之前已检查且不可用，直接走本地存储，不再重复连接
        if not self._check_minio():
            root = Path("uploads")
            root.mkdir(exist_ok=True)
            path = root / filename
            # 使用 aiofiles 异步写入，避免阻塞事件循环
            async with aiofiles.open(str(path), "wb") as f:
                await f.write(content)
            return f"/uploads/{filename}"

        # MinIO 上传放到线程池中执行（MinIO SDK 是同步的）
        loop = asyncio.get_running_loop()
        try:
            result = await loop.run_in_executor(
                None,
                self._upload_to_minio,
                filename,
                content,
                content_type,
                settings,
            )
            return result
        except Exception as exc:
            logger.warning("MinIO upload failed, fallback to local: {}", type(exc).__name__)
            # 标记 MinIO 不可用，后续不再尝试
            global _minio_available
            _minio_available = False
            root = Path("uploads")
            root.mkdir(exist_ok=True)
            path = root / filename
            async with aiofiles.open(str(path), "wb") as f:
                await f.write(content)
            return f"/uploads/{filename}"

    def _upload_to_minio(self, filename: str, content: bytes, content_type: str, settings) -> str:
        """同步上传到 MinIO（在 run_in_executor 中调用）。"""
        from minio import Minio

        client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        if not client.bucket_exists(settings.minio_bucket):
            client.make_bucket(settings.minio_bucket)
        client.put_object(
            settings.minio_bucket,
            filename,
            BytesIO(content),
            length=len(content),
            content_type=content_type,
        )
        scheme = "https" if settings.minio_secure else "http"
        return f"{scheme}://{settings.minio_endpoint}/{settings.minio_bucket}/{filename}"

    # 保留同步接口（兼容旧代码）
    def upload_image(self, filename: str, content: bytes, content_type: str) -> str:
        settings = get_settings()

        if not self._check_minio():
            root = Path("uploads")
            root.mkdir(exist_ok=True)
            path = root / filename
            path.write_bytes(content)
            return f"/uploads/{filename}"

        try:
            return self._upload_to_minio(filename, content, content_type, settings)
        except Exception as exc:
            logger.warning("MinIO upload failed, fallback to local: {}", type(exc).__name__)
            global _minio_available
            _minio_available = False
            root = Path("uploads")
            root.mkdir(exist_ok=True)
            path = root / filename
            path.write_bytes(content)
            return f"/uploads/{filename}"


storage_service = StorageService()
