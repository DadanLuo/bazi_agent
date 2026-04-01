# src/rag/retriever.py
"""
==============================================================================
命理知识检索器
==============================================================================

功能说明：
    本模块实现了基于向量数据库的知识检索功能，用于从命理知识库中检索
    相关的古籍知识和命理规则。使用 ChromaDB 作为向量数据库，通义千问
    的文本向量 API 进行向量化。

检索流程：
    1. 将查询文本转换为向量（使用 TextEmbedding API）
    2. 在 ChromaDB 中执行向量相似度检索
    3. 格式化检索结果为上下文文本

==============================================================================
"""

import os
import chromadb
from typing import List, Dict, Any
import dashscope
from dashscope import TextEmbedding
import logging

logger = logging.getLogger(__name__)

# 导入自定义模块
from src.config.rag_config import rag_config
from src.rag.metadata_extractor import extract_metadata
from src.rag.term_normalizer import normalize


class KnowledgeRetriever:
    """
    ==============================================================================
    命理知识检索器
    ==============================================================================
    
    功能说明：
        命理知识检索器，负责从向量数据库中检索相关的命理知识。
        使用 ChromaDB 作为向量数据库，通义千问的文本向量 API 进行向量化。
    
    核心方法：
        - get_embedding() - 获取文本的向量表示
        - search() - 检索相关知识
        - build_where_from_query() - 从查询构建过滤条件
        - format_context() - 格式化检索结果为上下文
    
    使用场景：
        - 八字分析时检索相关古籍知识
        - 塔罗占卜时检索相关知识
        - 提供 LLM 生成报告的参考依据
    
    ==============================================================================
    """

    def __init__(self, chroma_path: str | None = None, collection_name: str | None = None):
        """
        ==============================================================================
        初始化知识检索器
        ==============================================================================
        
        功能说明：
            初始化 ChromaDB 客户端和知识库集合。
        
        参数说明：
            chroma_path (str): ChromaDB 数据库存储路径
        
        环境变量：
            - DASHSCOPE_API_KEY: 阿里云 DashScope API Key（用于文本向量 API）
        
        异常：
            EnvironmentError: 如果 DASHSCOPE_API_KEY 未配置
        
        ==============================================================================
        """
        self.chroma_path = chroma_path or rag_config.chroma_persist_dir
        self.collection_name = collection_name or rag_config.collection_name
        self.embedding_model = rag_config.embedding_model
        self.client = chromadb.PersistentClient(path=self.chroma_path)
        try:
            self.collection = self.client.get_collection(name=self.collection_name)
        except Exception as e:
            raise RuntimeError(
                f"未找到当前 RAG 索引集合: {self.collection_name}。"
                "请先运行知识库构建脚本，或检查 RAG_INDEX_VERSION / RAG_COLLECTION_NAME 配置。"
            ) from e
        logger.info(
            "KnowledgeRetriever 初始化完成，集合=%s, embedding=%s, splitter=%s/%s",
            self.collection_name,
            rag_config.embedding_model,
            rag_config.splitter_name,
            rag_config.splitter_version,
        )

        # 配置 API
        self.api_key = os.getenv("DASHSCOPE_API_KEY")
        if not self.api_key:
            raise EnvironmentError("未设置 DASHSCOPE_API_KEY")
        dashscope.api_key = self.api_key

    def get_embedding(self, text: str) -> List[float]:
        """
        ==============================================================================
        获取文本的向量表示
        ==============================================================================
        
        功能说明：
            调用通义千问的文本向量 API，将文本转换为向量表示。
        
        参数说明：
            text (str): 要转换的文本
        
        返回值：
            List[float]: 文本的向量表示（1536 维）
        
        异常处理：
            - API 调用失败：返回空列表
            - 其他异常：打印错误信息并返回空列表
        
        ==============================================================================
        """
        try:
            response = TextEmbedding.call(
                model=self.embedding_model,
                input=[text]
            )
            if response.status_code == 200:
                return response.output['embeddings'][0]['embedding']
            else:
                raise RuntimeError(f"Embedding API 错误: {response.code}")
        except Exception as e:
            print(f"❌ 获取向量失败: {e}")
            return []

    def search(self, query: str, top_k: int = 5, where: Dict = None) -> List[Dict[str, Any]]:
        """
        ==============================================================================
        检索相关知识
        ==============================================================================
        
        功能说明：
            根据查询文本检索相关的命理知识。
        
        参数说明：
            query (str): 查询文本，如 "甲木生于寅月格局"
            top_k (int): 返回结果数量，默认 5
            where (Dict): 过滤条件，如 {"wuxing": {"$contains": "木"}, "topic": "格局"}
        
        返回值：
            List[Dict[str, Any]]: 检索结果列表，每个结果包含：
                - content (str): 文档内容
                - metadata (Dict): 元数据
                - distance (float): 向量距离（越小越相似）
        
        检索流程：
            1. 获取查询文本的向量表示
            2. 在 ChromaDB 中执行向量相似度检索（可选过滤条件）
            3. 格式化检索结果
        
        ==============================================================================
        """
        # 1. 获取查询向量
        query_embedding = self.get_embedding(query)
        if not query_embedding:
            return []

        # 2. 执行向量检索
        kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"]
        }
        if where:
            kwargs["where"] = where

        results = self.collection.query(**kwargs)

        # 3. 格式化结果
        formatted_results = []
        for i in range(len(results['documents'][0])):
            formatted_results.append({
                "content": results['documents'][0][i],
                "metadata": results['metadatas'][0][i],
                "distance": results['distances'][0][i]  # 距离越小越相似
            })

        return formatted_results

    def build_where_from_query(self, query: str) -> Dict:
        """
        ==============================================================================
        从查询文本构建 where 过滤条件
        ==============================================================================
        
        功能说明：
            从查询文本中提取关键实体，构建 ChromaDB 的 where 过滤条件。
            支持多级过滤和复杂的元数据匹配。
        
        参数说明：
            query (str): 查询文本
        
        返回值：
            Dict: where 过滤条件
        
        示例：
            输入: "甲木七杀格怎么成格"
            输出: {"tiangan": {"$contains": "甲"}, "wuxing": {"$contains": "木"}, "shensha": {"$contains": "七杀"}, "topic": "格局"}
        
        ==============================================================================
        """
        # 标准化查询文本
        normalized_query = normalize(query)
        
        # 提取 metadata
        metadata = extract_metadata(normalized_query)
        
        predicates = []

        def add_contains_predicate(field: str, values: List[str]) -> None:
            unique_values = [value for value in dict.fromkeys(values) if value]
            if not unique_values:
                return
            if len(unique_values) == 1:
                predicates.append({field: {"$contains": unique_values[0]}})
                return
            predicates.append({
                "$or": [{field: {"$contains": value}} for value in unique_values]
            })

        def add_equals_predicate(field: str, value: str) -> None:
            if value:
                predicates.append({field: value})

        add_contains_predicate("tiangan", metadata.get("tiangan", []))
        add_contains_predicate("dizhi", metadata.get("dizhi", []))
        add_contains_predicate("wuxing", metadata.get("wuxing", []))
        add_contains_predicate("shensha", metadata.get("shensha", []))
        add_contains_predicate("geju", metadata.get("geju", []))

        topic = metadata.get("topic")
        if topic and topic != "general":
            add_equals_predicate("topic", topic)

        sub_topic = metadata.get("sub_topic")
        if sub_topic and sub_topic != "general":
            add_equals_predicate("sub_topic", sub_topic)

        keywords = metadata.get("keywords", [])
        if keywords and len(keywords) <= 3:
            add_contains_predicate("keywords", keywords)

        if not predicates:
            return {}
        if len(predicates) == 1:
            return predicates[0]
        return {"$and": predicates}

    def format_context(self, results: List[Dict[str, Any]], max_length: int = 2000) -> str:
        """
        ==============================================================================
        将检索结果格式化为上下文文本
        ==============================================================================
        
        功能说明：
            将检索结果格式化为 LLM 可理解的上下文文本，用于提示词构建。
        
        参数说明：
            results (List[Dict[str, Any]]): search() 返回的结果
            max_length (int): 最大字符数，默认 2000
        
        返回值：
            str: 格式化后的上下文文本
        
        格式示例：
            【相关古籍参考】
            
            1. [文档内容]
            
            2. [文档内容]
            
            ...
        
        ==============================================================================
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

        # 使用新的过滤功能
        where_condition = retriever.build_where_from_query(query)
        print(f"FilterWhere: {where_condition}")
        
        results = retriever.search(query, top_k=3, where=where_condition)
        context = retriever.format_context(results)

        print(context[:500] + "...")
        print()
