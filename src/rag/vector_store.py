# src/rag/vector_store.py
import json
import os
from pathlib import Path
from typing import List, Dict, Any
import chromadb
from chromadb.config import Settings


class VectorStore:
    def __init__(self, persist_directory: str = "chroma_db"):
        self.persist_directory = persist_directory
        self.client = chromadb.PersistentClient(path=persist_directory)
        self.collection = self.client.get_or_create_collection(
            name="bazi_knowledge",
            metadata={"hnsw:space": "cosine"}
        )

    def build_from_processed_file(self, processed_file: str = "knowledge_base/processed/all_chunks.json"):
        """从预处理的 JSON 文件构建向量库（支持自动分批）"""
        processed_path = Path(processed_file).resolve()
        print(f"解析后的文件路径: {processed_path}")

        if not processed_path.exists():
            raise FileNotFoundError(f"预处理文件不存在: {processed_path}")

        with open(processed_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not data:
            raise ValueError("预处理数据为空")

        ids = [item["id"] for item in data]
        documents = [item["content"] for item in data]
        embeddings = [item["embedding"] for item in data]
        metadatas = [item["metadata"] for item in data]

        total_count = len(ids)
        print(f"📊 总数据量: {total_count} 条")

        # 关键修复：分批添加数据
        # ChromaDB 最大批次大小为 5461，我们使用 5000 作为安全阈值
        batch_size = 5000
        total_batches = (total_count + batch_size - 1) // batch_size

        for i in range(0, total_count, batch_size):
            end_idx = min(i + batch_size, total_count)
            batch_num = i // batch_size + 1

            print(f"⚡ 正在添加批次 [{batch_num}/{total_batches}] (记录 {i + 1}-{end_idx})")

            try:
                self.collection.add(
                    ids=ids[i:end_idx],
                    documents=documents[i:end_idx],
                    embeddings=embeddings[i:end_idx],
                    metadatas=metadatas[i:end_idx]
                )
            except Exception as e:
                print(f"❌ 批次 {batch_num} 添加失败: {e}")
                raise

        print(f"✅ 向量库构建完成，共 {total_count} 条记录")
        print(f"✅ 持久化路径: {self.persist_directory}")

    def query(self, query_embedding: List[float], n_results: int = 3) -> Dict[str, Any]:
        """执行向量检索"""
        return self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"]
        )

    def get_collection_count(self) -> int:
        """获取集合中的记录数量"""
        return self.collection.count()
