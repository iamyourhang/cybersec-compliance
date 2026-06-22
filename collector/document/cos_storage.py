"""
collector/document/cos_storage.py
COS 文件存储操作 - 只负责文件的上传、下载、删除、生成URL
不依赖任何业务逻辑
"""
from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Optional
from config.settings import get_settings

logger = logging.getLogger(__name__)


class CosStorage:
    """腾讯云 COS 操作封装"""

    def __init__(self):
        s = get_settings()
        self._bucket = s.cos.bucket
        self._region = s.cos.region
        self._client = self._build_client(s)

    def _build_client(self, s):
        from qcloud_cos import CosConfig, CosS3Client
        config = CosConfig(
            Region=s.cos.region,
            SecretId=s.cos.secret_id,
            SecretKey=s.cos.secret_key,
            Timeout=int(os.getenv("COS_CLIENT_TIMEOUT_SECONDS", "300")),
        )
        return CosS3Client(config)

    def upload_file(self, local_path: str, cos_key: str) -> str:
        """上传本地文件到COS，返回访问URL"""
        with open(local_path, "rb") as f:
            self._client.put_object(
                Bucket=self._bucket,
                Body=f,
                Key=cos_key,
            )
        url = f"https://{self._bucket}.cos.{self._region}.myqcloud.com/{cos_key}"
        logger.info("✅ COS上传成功: %s -> %s", local_path, cos_key)
        return url

    def upload_bytes(self, data: bytes, cos_key: str) -> str:
        """上传字节数据到COS，返回访问URL"""
        self._client.put_object(
            Bucket=self._bucket,
            Body=data,
            Key=cos_key,
        )
        url = f"https://{self._bucket}.cos.{self._region}.myqcloud.com/{cos_key}"
        logger.info("✅ COS上传成功: %s (%d bytes)", cos_key, len(data))
        return url

    def download_bytes(self, cos_key: str) -> bytes:
        """从COS下载文件，返回字节数据"""
        resp = self._client.get_object(Bucket=self._bucket, Key=cos_key)
        data = resp["Body"].get_raw_stream().read()
        logger.info("✅ COS下载成功: %s (%d bytes)", cos_key, len(data))
        return data

    def delete(self, cos_key: str) -> None:
        """删除COS文件"""
        self._client.delete_object(Bucket=self._bucket, Key=cos_key)
        logger.info("🗑️  COS删除: %s", cos_key)

    def exists(self, cos_key: str) -> bool:
        """检查文件是否存在"""
        try:
            self._client.head_object(Bucket=self._bucket, Key=cos_key)
            return True
        except Exception:
            return False

    def get_url(self, cos_key: str) -> str:
        """获取文件访问URL"""
        return f"https://{self._bucket}.cos.{self._region}.myqcloud.com/{cos_key}"
