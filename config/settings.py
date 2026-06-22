"""
config/settings.py
全局配置加载 - 基于 pydantic-settings，类型安全，支持 .env 文件
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录
BASE_DIR = Path(__file__).parent.parent


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DB_", extra="ignore")

    host: str = "localhost"
    port: int = 5432
    name: str = "cybersec_compliance"
    user: str = "compliance_user"
    password: str = ""
    pool_min: int = 2
    pool_max: int = 10

    @property
    def dsn(self) -> str:
        return (
            f"postgresql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )

    @property
    def async_dsn(self) -> str:
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )


class VolcengineSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VOLCENGINE_", extra="ignore")

    api_key: str = ""
    base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    model_primary: str = "doubao-seed-2.0-pro"
    model_fallback: str = "doubao-seed-2.0-lite"


class DashscopeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DASHSCOPE_", extra="ignore")

    api_key: str = ""
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    model: str = "qwen-max"


class DeepseekSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DEEPSEEK_", extra="ignore")

    api_key: str = ""
    base_url: str = "https://api.deepseek.com/v1"
    model: str = "deepseek-chat"


class UniapiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="UNIAPI_", extra="ignore")

    api_key: str = ""
    base_url: str = "https://uniapi.ruijie.com.cn/"
    model: str = ""


class EmbeddingSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EMBEDDING_", extra="ignore")

    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "text-embedding-3-small"
    dimensions: int = 1536


class FeishuSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FEISHU_", extra="ignore")

    webhook_url: str = ""
    webhook_secret: str = ""
    app_id: str = ""
    app_secret: str = ""
    verification_token: str = ""


class CosSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="COS_", extra="ignore")

    secret_id: str = ""
    secret_key: str = ""
    bucket: str = ""
    region: str = "ap-guangzhou"
    report_prefix: str = "reports/"


class AdminSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ADMIN_", extra="ignore")

    username: str = "admin"
    password: str = ""
    super_username: str = ""
    super_password: str = ""
    users_json: str = ""
    ip_whitelist_raw: str = Field("127.0.0.1", alias="ADMIN_IP_WHITELIST")
    jwt_secret: str = ""
    port: int = 8080

    @property
    def ip_whitelist(self) -> List[str]:
        return [ip.strip() for ip in self.ip_whitelist_raw.split(",") if ip.strip()]

    model_config = SettingsConfigDict(env_prefix="ADMIN_", extra="ignore", populate_by_name=True)


class ScheduleSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SCHEDULE_", extra="ignore")

    full_update: str = "0 1 * * 1"
    incremental: str = "0 2 * * *"
    weekly_report: str = "0 9 * * 1"


class DiscoverySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DISCOVERY_", extra="ignore")

    search_backend: str = "responses_web_search"
    web_search_model: str = "gpt-5.4-mini"
    web_search_timeout: int = 90


class LogSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LOG_", extra="ignore")

    level: str = "INFO"
    dir: str = "logs"
    retention_days: int = 30


class Settings(BaseSettings):
    """主配置类，聚合所有子配置"""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / "config" / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: str = "production"
    llm_router_secret: str = Field("", alias="LLM_ROUTER_SECRET")
    llm_router_fallback_json: str = Field("[]", alias="LLM_ROUTER_FALLBACK_JSON")

    # 子配置（通过实例化加载各自前缀的环境变量）
    @property
    def db(self) -> DatabaseSettings:
        return _load_sub(DatabaseSettings)

    @property
    def volcengine(self) -> VolcengineSettings:
        return _load_sub(VolcengineSettings)

    @property
    def dashscope(self) -> DashscopeSettings:
        return _load_sub(DashscopeSettings)

    @property
    def deepseek(self) -> DeepseekSettings:
        return _load_sub(DeepseekSettings)

    @property
    def uniapi(self) -> UniapiSettings:
        return _load_sub(UniapiSettings)

    @property
    def embedding(self) -> EmbeddingSettings:
        return _load_sub(EmbeddingSettings)

    @property
    def feishu(self) -> FeishuSettings:
        return _load_sub(FeishuSettings)

    @property
    def cos(self) -> CosSettings:
        return _load_sub(CosSettings)

    @property
    def admin(self) -> AdminSettings:
        return _load_sub(AdminSettings)

    @property
    def schedule(self) -> ScheduleSettings:
        return _load_sub(ScheduleSettings)

    @property
    def discovery(self) -> DiscoverySettings:
        return _load_sub(DiscoverySettings)

    @property
    def log(self) -> LogSettings:
        return _load_sub(LogSettings)

    @property
    def is_dev(self) -> bool:
        return self.env.lower() == "development"

    @property
    def llm_router_fallback(self) -> List[dict[str, Any]]:
        raw = self.llm_router_fallback_json
        if not raw.strip():
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("LLM_ROUTER_FALLBACK_JSON 不是合法 JSON") from exc
        if not isinstance(data, list):
            raise ValueError("LLM_ROUTER_FALLBACK_JSON 必须是 JSON 数组")
        return data


def _load_sub(cls):
    """加载子配置，自动读取 .env 文件"""
    env_file = BASE_DIR / "config" / ".env"
    return cls(
        _env_file=str(env_file) if env_file.exists() else None,
        _env_file_encoding="utf-8",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """获取全局配置单例（带缓存）"""
    return Settings()


# 便捷访问
settings = get_settings()
