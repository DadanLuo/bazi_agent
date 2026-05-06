"""RAG 版本隔离配置。

将向量库集合名、Embedding 模型、切分器版本和增量构建记录绑定到同一套配置，
避免新旧索引在同一个 Chroma collection 中混用。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional

from config.settings import settings


def _slug_token(value: str, max_len: int) -> str:
    """将任意字符串转换为安全、短小的 collection name 片段。"""
    normalized = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    if not normalized:
        normalized = "default"
    return normalized[:max_len].strip("_") or "default"


def _fingerprint(payload: Dict[str, str]) -> str:
    """生成稳定短哈希，用于隔离不同索引配置。"""
    serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(serialized.encode("utf-8")).hexdigest()[:8]


def build_collection_name(
    collection_prefix: str,
    index_version: str,
    embedding_provider: str,
    embedding_model: str,
    splitter_name: str,
    splitter_version: str,
    explicit_collection_name: Optional[str] = None,
) -> str:
    """根据当前 RAG 配置生成稳定的 collection 名称。"""
    if explicit_collection_name:
        return explicit_collection_name

    payload = {
        "index_version": index_version,
        "embedding_provider": embedding_provider,
        "embedding_model": embedding_model,
        "splitter_name": splitter_name,
        "splitter_version": splitter_version,
    }
    fingerprint = _fingerprint(payload)

    prefix_token = _slug_token(collection_prefix, 16)
    version_token = _slug_token(index_version, 8)
    model_token = _slug_token(embedding_model, 12)
    splitter_token = _slug_token(splitter_name, 10)

    return (
        f"{prefix_token}_{version_token}_{model_token}_{splitter_token}_{fingerprint}"
    )


@dataclass(frozen=True)
class RagVersionSettings:
    """当前 RAG 索引配置。"""

    chroma_persist_dir: str
    collection_prefix: str
    index_version: str
    embedding_provider: str
    embedding_model: str
    splitter_name: str
    splitter_version: str
    explicit_collection_name: Optional[str] = None

    @property
    def fingerprint(self) -> str:
        return _fingerprint(
            {
                "index_version": self.index_version,
                "embedding_provider": self.embedding_provider,
                "embedding_model": self.embedding_model,
                "splitter_name": self.splitter_name,
                "splitter_version": self.splitter_version,
            }
        )

    @property
    def collection_name(self) -> str:
        return build_collection_name(
            collection_prefix=self.collection_prefix,
            index_version=self.index_version,
            embedding_provider=self.embedding_provider,
            embedding_model=self.embedding_model,
            splitter_name=self.splitter_name,
            splitter_version=self.splitter_version,
            explicit_collection_name=self.explicit_collection_name,
        )

    @property
    def collection_alias(self) -> str:
        return (
            f"{self.collection_prefix}:{self.index_version}:"
            f"{self.embedding_provider}/{self.embedding_model}:"
            f"{self.splitter_name}/{self.splitter_version}"
        )

    @property
    def collection_metadata(self) -> Dict[str, str]:
        return {
            "hnsw:space": "cosine",
            "index_version": self.index_version,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "splitter_name": self.splitter_name,
            "splitter_version": self.splitter_version,
            "config_fingerprint": self.fingerprint,
            "collection_alias": self.collection_alias,
        }

    @property
    def md5_record_file(self) -> Path:
        project_root = Path(__file__).resolve().parents[2]
        processed_dir = project_root / "knowledge_base" / "processed"
        return processed_dir / f"processed_files_md5_{self.collection_name}.json"


def load_rag_config() -> RagVersionSettings:
    """从统一 config 加载当前 RAG 配置。"""
    return RagVersionSettings(
        chroma_persist_dir=settings.resolved_chroma_persist_dir,
        collection_prefix=settings.resolved_rag_collection_prefix,
        index_version=settings.resolved_rag_index_version,
        embedding_provider=settings.resolved_embedding_provider,
        embedding_model=settings.resolved_embedding_model,
        splitter_name=settings.resolved_rag_splitter_name,
        splitter_version=settings.resolved_rag_splitter_version,
        explicit_collection_name=settings.resolved_rag_collection_name,
    )


rag_config = load_rag_config()
