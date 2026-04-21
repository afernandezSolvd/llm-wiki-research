import hashlib
import os
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

import aiofiles

from app.config import get_settings
from app.core.exceptions import StorageError

settings = get_settings()


class StorageBackend(ABC):
    @abstractmethod
    async def upload(self, data: bytes, filename: str, content_type: str) -> tuple[str, str]:
        """Upload data. Returns (storage_key, content_hash)."""

    @abstractmethod
    async def download(self, storage_key: str) -> bytes:
        """Download raw bytes for a storage key."""

    @abstractmethod
    async def delete(self, storage_key: str) -> None:
        pass


class LocalStorageBackend(StorageBackend):
    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    async def upload(self, data: bytes, filename: str, content_type: str) -> tuple[str, str]:
        content_hash = hashlib.sha256(data).hexdigest()
        key = f"{uuid.uuid4().hex}/{filename}"
        dest = self.root / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(dest, "wb") as f:
            await f.write(data)
        return key, content_hash

    async def download(self, storage_key: str) -> bytes:
        path = self.root / storage_key
        if not path.exists():
            raise StorageError(f"Key not found: {storage_key}")
        async with aiofiles.open(path, "rb") as f:
            return await f.read()

    async def delete(self, storage_key: str) -> None:
        path = self.root / storage_key
        if path.exists():
            os.remove(path)


class S3StorageBackend(StorageBackend):
    def __init__(self):
        import boto3
        self._s3 = boto3.client(
            "s3",
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region,
        )
        self._bucket = settings.aws_s3_bucket

    async def upload(self, data: bytes, filename: str, content_type: str) -> tuple[str, str]:
        content_hash = hashlib.sha256(data).hexdigest()
        key = f"{uuid.uuid4().hex}/{filename}"
        self._s3.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        return key, content_hash

    async def download(self, storage_key: str) -> bytes:
        try:
            resp = self._s3.get_object(Bucket=self._bucket, Key=storage_key)
            return resp["Body"].read()
        except Exception as e:
            raise StorageError(f"S3 download failed: {e}") from e

    async def delete(self, storage_key: str) -> None:
        self._s3.delete_object(Bucket=self._bucket, Key=storage_key)


def get_storage() -> StorageBackend:
    if settings.storage_backend == "s3":
        return S3StorageBackend()
    return LocalStorageBackend(settings.storage_local_root)
