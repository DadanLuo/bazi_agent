"""
项目主配置文件
使用 pydantic-settings 管理环境变量
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _normalize_env_value(value: Optional[str]) -> Optional[str]:
    """清洗环境变量值，忽略空串和未展开的占位符。"""
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if cleaned.startswith("${") and cleaned.endswith("}"):
        return None
    return cleaned


def _first_text(*values: Optional[str]) -> Optional[str]:
    for value in values:
        cleaned = _normalize_env_value(value)
        if cleaned is not None:
            return cleaned
    return None


def _read_env_value(*keys: str) -> Optional[str]:
    for key in keys:
        value = _normalize_env_value(os.getenv(key))
        if value is not None:
            return value
    return None


def _read_env_int(*keys: str, default: int) -> int:
    for key in keys:
        value = _read_env_value(key)
        if value is None:
            continue
        try:
            return int(value)
        except ValueError:
            continue
    return default


def _read_env_float(*keys: str, default: float) -> float:
    for key in keys:
        value = _read_env_value(key)
        if value is None:
            continue
        try:
            return float(value)
        except ValueError:
            continue
    return default


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ===== 基础配置 =====
    APP_NAME: str = "赛博司命"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = Field(default="development", env="APP_ENV")
    DEBUG: bool = Field(default=True, env="DEBUG")

    # ===== 路径配置 =====
    BASE_DIR: Path = Field(default=Path(__file__).parent.parent)
    DATA_DIR: Path = Field(default=Path("./data"))
    LOGS_DIR: Path = Field(default=Path("./logs"))
    KNOWLEDGE_BASE_DIR: Path = Field(default=Path("./knowledge_base"))

    # ===== 大模型配置（通义千问）=====
    LLM_PROVIDER: str = Field(default="qwen", env="LLM_PROVIDER")
    DASHSCOPE_API_KEY: Optional[str] = Field(default=None, env="DASHSCOPE_API_KEY")
    QWEN_API_KEY: Optional[str] = Field(default=None, env="QWEN_API_KEY")
    QWEN_BASE_URL: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        env="QWEN_BASE_URL"
    )
    LLM_MODEL_NAME: Optional[str] = Field(default=None, env="LLM_MODEL_NAME")
    QWEN_MODEL: str = Field(default="qwen3.5-plus", env="QWEN_MODEL")
    QWEN_CONTEXT_WINDOW: Optional[int] = Field(default=None, env="QWEN_CONTEXT_WINDOW")
    LLM_CONTEXT_WINDOW: int = Field(default=262144, env="LLM_CONTEXT_WINDOW")

    # ===== 数据库配置 =====
    DATABASE_URL: Optional[str] = Field(default=None, env="DATABASE_URL")
    SQLITE_PATH: str = Field(default="./data/checkpoints.db", env="SQLITE_PATH")

    # ===== RAG 配置 =====
    CHROMA_PERSIST_DIR: str = Field(
        default="./knowledge_base/vector_store",
        env="CHROMA_PERSIST_DIR"
    )
    EMBEDDING_MODEL: str = Field(
        default="text-embedding-v4",
        env="EMBEDDING_MODEL"
    )
    RAG_COLLECTION_PREFIX: str = Field(default="bazi_knowledge", env="RAG_COLLECTION_PREFIX")
    RAG_INDEX_VERSION: str = Field(default="v2", env="RAG_INDEX_VERSION")
    RAG_EMBEDDING_PROVIDER: str = Field(default="dashscope", env="RAG_EMBEDDING_PROVIDER")
    RAG_EMBEDDING_MODEL: Optional[str] = Field(default=None, env="RAG_EMBEDDING_MODEL")
    RAG_SPLITTER_NAME: str = Field(default="recursive", env="RAG_SPLITTER_NAME")
    RAG_SPLITTER_VERSION: str = Field(default="v1", env="RAG_SPLITTER_VERSION")
    RAG_COLLECTION_NAME: Optional[str] = Field(default=None, env="RAG_COLLECTION_NAME")
    CHUNK_SIZE: int = Field(default=800, env="CHUNK_SIZE")
    CHUNK_OVERLAP: int = Field(default=200, env="CHUNK_OVERLAP")

    # ===== LangGraph 配置 =====
    CHECKPOINT_TYPE: str = Field(default="sqlite", env="CHECKPOINT_TYPE")
    THREAD_TTL_SECONDS: int = Field(default=3600, env="THREAD_TTL_SECONDS")

    # ===== 安全配置 =====
    SENSITIVE_KEYWORDS: List[str] = Field(
        default=[
            "自杀", "死亡", "灾难", "血光", "官司",
            "赌博", "投资", "医疗", "怀孕", "堕胎"
        ],
        env="SENSITIVE_KEYWORDS"
    )
    HUMAN_REVIEW_THRESHOLD: float = Field(default=0.8, env="HUMAN_REVIEW_THRESHOLD")

    # ===== 日志配置 =====
    LOG_LEVEL: str = Field(default="INFO", env="LOG_LEVEL")

    # ===== 性能配置 =====
    LLM_MAX_TOKENS: Optional[int] = Field(default=None, env="LLM_MAX_TOKENS")
    MAX_TOKENS: int = Field(default=16384, env="MAX_TOKENS")
    LLM_TEMPERATURE: Optional[float] = Field(default=None, env="LLM_TEMPERATURE")
    TEMPERATURE: float = Field(default=0.7, env="TEMPERATURE")
    LLM_TIMEOUT: Optional[int] = Field(default=None, env="LLM_TIMEOUT")
    REQUEST_TIMEOUT: int = Field(default=120, env="REQUEST_TIMEOUT")
    LLM_MAX_RETRIES: int = Field(default=1, env="LLM_MAX_RETRIES")

    # ===== 阿里云内容安全配置 =====
    ALIYUN_ACCESS_KEY_ID: Optional[str] = Field(default=None, env="ALIYUN_ACCESS_KEY_ID")
    ALIYUN_ACCESS_KEY_SECRET: Optional[str] = Field(
        default=None,
        env="ALIYUN_ACCESS_KEY_SECRET",
    )
    ALIYUN_GREEN_ENDPOINT: str = Field(
        default="green-cip.cn-shanghai.aliyuncs.com",
        env="ALIYUN_GREEN_ENDPOINT",
    )

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def resolved_qwen_api_key(self) -> Optional[str]:
        return _first_text(
            _read_env_value("QWEN_API_KEY", "DASHSCOPE_API_KEY"),
            self.QWEN_API_KEY,
            self.DASHSCOPE_API_KEY,
        )

    @property
    def resolved_llm_base_url(self) -> str:
        return _first_text(
            _read_env_value("QWEN_BASE_URL"),
            self.QWEN_BASE_URL,
        ) or "https://dashscope.aliyuncs.com/compatible-mode/v1"

    @property
    def resolved_llm_model_name(self) -> str:
        return _first_text(
            _read_env_value("LLM_MODEL_NAME", "QWEN_MODEL"),
            self.LLM_MODEL_NAME,
            self.QWEN_MODEL,
        ) or "qwen3.5-plus"

    @property
    def resolved_llm_context_window(self) -> int:
        return _read_env_int(
            "LLM_CONTEXT_WINDOW",
            "QWEN_CONTEXT_WINDOW",
            default=self.LLM_CONTEXT_WINDOW or self.QWEN_CONTEXT_WINDOW or 262144,
        )

    @property
    def resolved_llm_max_tokens(self) -> int:
        return _read_env_int(
            "LLM_MAX_TOKENS",
            "MAX_TOKENS",
            default=self.LLM_MAX_TOKENS or self.MAX_TOKENS,
        )

    @property
    def resolved_llm_temperature(self) -> float:
        return _read_env_float(
            "LLM_TEMPERATURE",
            "TEMPERATURE",
            default=self.LLM_TEMPERATURE or self.TEMPERATURE,
        )

    @property
    def resolved_llm_timeout(self) -> int:
        return _read_env_int(
            "LLM_TIMEOUT",
            "REQUEST_TIMEOUT",
            default=self.LLM_TIMEOUT or self.REQUEST_TIMEOUT,
        )

    @property
    def resolved_llm_max_retries(self) -> int:
        return _read_env_int("LLM_MAX_RETRIES", default=self.LLM_MAX_RETRIES)

    @property
    def resolved_embedding_provider(self) -> str:
        return _first_text(
            _read_env_value("RAG_EMBEDDING_PROVIDER"),
            self.RAG_EMBEDDING_PROVIDER,
        ) or "dashscope"

    @property
    def resolved_embedding_model(self) -> str:
        return _first_text(
            _read_env_value("RAG_EMBEDDING_MODEL", "EMBEDDING_MODEL"),
            self.RAG_EMBEDDING_MODEL,
            self.EMBEDDING_MODEL,
        ) or "text-embedding-v4"

    @property
    def resolved_embedding_api_key(self) -> Optional[str]:
        return self.resolved_qwen_api_key

    @property
    def resolved_chroma_persist_dir(self) -> str:
        return _first_text(
            _read_env_value("CHROMA_PERSIST_DIR"),
            self.CHROMA_PERSIST_DIR,
        ) or "./knowledge_base/vector_store"

    @property
    def resolved_rag_collection_prefix(self) -> str:
        return _first_text(
            _read_env_value("RAG_COLLECTION_PREFIX"),
            self.RAG_COLLECTION_PREFIX,
        ) or "bazi_knowledge"

    @property
    def resolved_rag_index_version(self) -> str:
        return _first_text(
            _read_env_value("RAG_INDEX_VERSION"),
            self.RAG_INDEX_VERSION,
        ) or "v2"

    @property
    def resolved_rag_splitter_name(self) -> str:
        return _first_text(
            _read_env_value("RAG_SPLITTER_NAME"),
            self.RAG_SPLITTER_NAME,
        ) or "recursive"

    @property
    def resolved_rag_splitter_version(self) -> str:
        return _first_text(
            _read_env_value("RAG_SPLITTER_VERSION"),
            self.RAG_SPLITTER_VERSION,
        ) or "v1"

    @property
    def resolved_rag_collection_name(self) -> Optional[str]:
        return _first_text(
            _read_env_value("RAG_COLLECTION_NAME"),
            self.RAG_COLLECTION_NAME,
        )

    @property
    def resolved_aliyun_access_key_id(self) -> Optional[str]:
        return _first_text(
            _read_env_value("ALIYUN_ACCESS_KEY_ID"),
            self.ALIYUN_ACCESS_KEY_ID,
            self.resolved_qwen_api_key,
        )

    @property
    def resolved_aliyun_access_key_secret(self) -> Optional[str]:
        return _first_text(
            _read_env_value("ALIYUN_ACCESS_KEY_SECRET"),
            self.ALIYUN_ACCESS_KEY_SECRET,
        )

    @property
    def resolved_aliyun_green_endpoint(self) -> str:
        return _first_text(
            _read_env_value("ALIYUN_GREEN_ENDPOINT"),
            self.ALIYUN_GREEN_ENDPOINT,
        ) or "green-cip.cn-shanghai.aliyuncs.com"

    @property
    def llm_config(self) -> dict:
        """获取统一 LLM 配置。"""
        return {
            "api_key": self.resolved_qwen_api_key,
            "base_url": self.resolved_llm_base_url,
            "model": self.resolved_llm_model_name,
            "context_window": self.resolved_llm_context_window,
            "temperature": self.resolved_llm_temperature,
            "max_tokens": self.resolved_llm_max_tokens,
            "max_retries": self.resolved_llm_max_retries,
        }

    @property
    def rag_config(self) -> dict:
        """获取统一 RAG / Embedding 配置。"""
        return {
            "chroma_persist_dir": self.resolved_chroma_persist_dir,
            "collection_prefix": self.resolved_rag_collection_prefix,
            "index_version": self.resolved_rag_index_version,
            "embedding_provider": self.resolved_embedding_provider,
            "embedding_model": self.resolved_embedding_model,
            "embedding_api_key": self.resolved_embedding_api_key,
            "splitter_name": self.resolved_rag_splitter_name,
            "splitter_version": self.resolved_rag_splitter_version,
            "explicit_collection_name": self.resolved_rag_collection_name,
        }

    def ensure_dirs(self):
        """确保所有必要目录存在"""
        for dir_path in [self.DATA_DIR, self.LOGS_DIR, self.KNOWLEDGE_BASE_DIR]:
            dir_path.mkdir(parents=True, exist_ok=True)


# 单例配置实例
settings = Settings()

# 初始化目录
settings.ensure_dirs()
