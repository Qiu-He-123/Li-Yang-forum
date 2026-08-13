import asyncio
import json
from io import BytesIO
from pathlib import Path

import aiofiles
from loguru import logger

from app.core.config import get_settings

# T8-1：缓存 MinIO 不可用状态，避免每次上传都尝试连接（每次超时 30 秒）
_minio_checked: bool = False
_minio_available: bool = False

# P0-1：私密图片（学生证等）本地存储目录，与公开 uploads/ 完全隔离
PRIVATE_DIR = "uploads_private"


def _public_bucket_policy(bucket: str) -> str:
    """公开图片桶的只读策略（帖子图片本身需要公开展示）。"""
    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket}/*"],
                }
            ],
        }
    )


class StorageService:
    def _new_client(self, settings):
        from minio import Minio
        from urllib3 import PoolManager

        return Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
            # 显式短超时 + 关闭重试：MinIO 不在线时秒级失败，不再让
            # 检查线程在后台空转 30 秒
            http_client=PoolManager(
                timeout=2.0,
                retries=False,
            ),
        )

    def _check_minio(self) -> bool:
        """检查 MinIO 是否可用，结果缓存避免重复连接。"""
        global _minio_checked, _minio_available
        if _minio_checked:
            return _minio_available

        settings = get_settings()
        if not settings.minio_endpoint:
            _minio_checked = True
            _minio_available = False
            return False
        try:
            client = self._new_client(settings)

            # 用短超时检查 bucket 是否存在（3秒超时，避免长时间阻塞）
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
        """上传公开图片：本地 uploads/ 或 MinIO 公开桶（同源 /minio/* 可访问）。"""
        settings = get_settings()

        if not self._check_minio():
            path = Path("uploads") / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(str(path), "wb") as f:
                await f.write(content)
            return f"/uploads/{filename}"

        # MinIO 上传放到线程池中执行（MinIO SDK 是同步的）
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(
                None,
                self._upload_to_minio,
                filename,
                content,
                content_type,
                settings,
            )
        except Exception as exc:
            logger.warning("MinIO upload failed, fallback to local: {}", type(exc).__name__)
            global _minio_available
            _minio_available = False
            path = Path("uploads") / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            async with aiofiles.open(str(path), "wb") as f:
                await f.write(content)
            return f"/uploads/{filename}"

    async def upload_private_image_async(self, filename: str, content: bytes, content_type: str) -> str:
        """上传私密图片（学生证等敏感照片）。

        - 本地存 uploads_private/（不挂载公开静态目录）
        - MinIO 存私有桶（默认私有策略），URL 统一走 /images/private/* 鉴权转发
        """
        settings = get_settings()
        if not self._check_minio():
            root = Path(PRIVATE_DIR)
            root.mkdir(exist_ok=True)
            path = root / filename
            async with aiofiles.open(str(path), "wb") as f:
                await f.write(content)
            return f"/images/private/{filename}"

        try:
            await asyncio.to_thread(
                self._upload_private_to_minio,
                filename,
                content,
                content_type,
                settings,
            )
        except Exception as exc:
            logger.warning("MinIO private upload failed, fallback to local: {}", type(exc).__name__)
            global _minio_available
            _minio_available = False
            root = Path(PRIVATE_DIR)
            root.mkdir(exist_ok=True)
            path = root / filename
            async with aiofiles.open(str(path), "wb") as f:
                await f.write(content)
        return f"/images/private/{filename}"

    async def read_private(self, filename: str) -> bytes | None:
        """读取私密图片字节（本地文件或 MinIO 私有桶），不存在返回 None。"""
        if self._check_minio():
            try:
                settings = get_settings()
                client = self._new_client(settings)
                resp = client.get_object(settings.minio_private_bucket, filename)
                try:
                    return resp.read()
                finally:
                    resp.close()
                    resp.release_conn()
            except Exception as exc:
                logger.warning("MinIO private read failed, fallback to local: {}", type(exc).__name__)

        private_root = Path(PRIVATE_DIR).resolve()
        path = (private_root / filename).resolve()
        # 防路径穿越：必须位于私有目录内
        if not path.is_relative_to(private_root) or not path.exists():
            return None
        return path.read_bytes()

    def _upload_to_minio(self, filename: str, content: bytes, content_type: str, settings) -> str:
        """同步上传公开图片到 MinIO（公开桶 + 只读策略），返回同源相对 URL。"""
        client = self._new_client(settings)
        bucket = settings.minio_bucket
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        client.set_bucket_policy(bucket, _public_bucket_policy(bucket))
        client.put_object(
            bucket,
            filename,
            BytesIO(content),
            length=len(content),
            content_type=content_type,
        )
        # 同源相对路径：由 Nginx /minio/ 反代到 MinIO，避免浏览器无法解析容器主机名
        return f"/minio/{bucket}/{filename}"

    def _upload_private_to_minio(self, filename: str, content: bytes, content_type: str, settings) -> None:
        """同步上传私密图片到 MinIO 私有桶（默认私有策略，不设置公开读）。"""
        client = self._new_client(settings)
        bucket = settings.minio_private_bucket
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        client.put_object(
            bucket,
            filename,
            BytesIO(content),
            length=len(content),
            content_type=content_type,
        )

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
