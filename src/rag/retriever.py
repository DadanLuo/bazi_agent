# src/rag/retriever.py
import os
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any
import dashscope
from dashscope import TextEmbedding


class KnowledgeRetriever:
    """命理知识检索器"""

    def __init__(self, chroma_path: str = "D:/bazi-agent/chroma_db"):
        self.client = chromadb.PersistentClient(path=chroma_path)
        self.collection = self.client.get_collection(name="bazi_knowledge")

        # 配置 API
        self.api_key = os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            raise EnvironmentError("未设置 DASHSCOPE_API_KEY")
        dashscope.api_key = self.api_key

    def get_embedding(self, text: str) -> List[float]:
        """获取文本的向量表示"""
        try:
            response = TextEmbedding.call(
                model="text-embedding-v4",
                input=[text]
            )
            if response.status_code == 200:
                return response.output['embeddings'][0]['embedding']
            else:
                raise RuntimeError(f"Embedding API 错误: {response.code}")
        except Exception as e:
            print(f"❌ 获取向量失败: {e}")
            return []

    def search(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        检索相关知识

        Args:
            query: 查询文本，如 "甲木生于寅月格局"
            top_k: 返回结果数量

        Returns:
            包含文档内容和元数据的列表
        """
        # 1. 获取查询向量
        query_embedding = self.get_embedding(query)
        if not query_embedding:
            return []

        # 2. 执行向量检索
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )

        # 3. 格式化结果
        formatted_results = []
        for i in range(len(results['documents'][0])):
            formatted_results.append({
                "content": results['documents'][0][i],
                "metadata": results['metadatas'][0][i],
                "distance": results['distances'][0][i]  # 距离越小越相似
            })

        return formatted_results

    def format_context(self, results: List[Dict[str, Any]], max_length: int = 2000) -> str:
        """
        将检索结果格式化为上下文文本

        Args:
            results: search() 返回的结果
            max_length: 最大字符数

        Returns:
            格式化后的上下文
        """
        context = "【相关古籍参考】\n\n"
        current_length = len(context)

        for i, item in enumerate(results, 1):
            snippet = f"{i}. {item['content']}\n\n"

            if current_length + len(snippet) > max_length:
                break

            context += snippet
            current_length += len(snippet)

        return context


# 测试检索器
if __name__ == "__main__":
    print("=" * 60)
    print("🔍 测试知识检索")
    print("=" * 60)

    retriever = KnowledgeRetriever()

    # 测试查询
    queries = [
        "甲木生于寅月",
        "财格成格条件",
        "七杀有制"
        
    ]

    for query in queries:
        print(f"\n🔎 查询: {query}")
        print("-" * 60)

        results = retriever.search(query, top_k=3)
        context = retriever.format_context(results)

        print(context[:500] + "...")
        print()
