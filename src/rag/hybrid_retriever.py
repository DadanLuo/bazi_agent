# src/rag/hybrid_retriever.py
"""混合检索器 - Vector + BM25 + Rerank"""
from typing import Dict, Any, List, Optional
import math

from src.config.rag_config import RAGConfigManager
from src.rag.retriever import KnowledgeRetriever
from src.rag.bm25_retriever import BM25Retriever
from src.rag.reranker import Reranker


class HybridRetriever:
    """混合检索器，结合向量检索、BM25检索和重排序"""
    
    def __init__(
        self,
        vector_retriever: Optional[KnowledgeRetriever] = None,
        bm25_retriever: Optional[BM25Retriever] = None,
        reranker: Optional[Reranker] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """初始化混合检索器"""
        self.config = config or RAGConfigManager.get_hybrid_config()
        
        # 初始化各检索器
        self.vector_retriever = vector_retriever or KnowledgeRetriever()
        self.bm25_retriever = bm25_retriever or BM25Retriever()
        self.reranker = reranker or Reranker()
        
        # 混合检索参数
        self.vector_weight = self.config.get("vector_weight", 0.6)
        self.bm25_weight = self.config.get("bm25_weight", 0.4)
        self.candidate_multiplier = self.config.get("candidate_multiplier", 4)
        self.rerank_top_k = self.config.get("rerank_top_k", 5)
        
        # 检索模式
        self.retrieval_mode = RAGConfigManager.get_retrieval_mode()
    
    def _normalize_scores(self, scores: List[float]) -> List[float]:
        """归一化分数到 [0, 1]"""
        if not scores:
            return []
        
        min_score = min(scores)
        max_score = max(scores)
        
        if max_score == min_score:
            return [1.0] * len(scores)
        
        return [(s - min_score) / (max_score - min_score) for s in scores]
    
    def _fuse_scores(
        self,
        vector_results: List[Dict[str, Any]],
        bm25_results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """融合向量检索和BM25检索结果"""
        # 创建文档ID到结果的映射
        vector_docs = {r["id"]: r for r in vector_results}
        bm25_docs = {r["id"]: r for r in bm25_results}
        
        # 获取所有唯一文档ID
        all_ids = set(vector_docs.keys()) | set(bm25_docs.keys())
        
        # 计算融合分数
        fused_results = []
        for doc_id in all_ids:
            vector_score = vector_docs.get(doc_id, {}).get("score", 0)
            bm25_score = bm25_docs.get(doc_id, {}).get("score", 0)
            
            # 归一化分数
            vector_norm = vector_docs.get(doc_id, {}).get("normalized_score", 0)
            bm25_norm = bm25_docs.get(doc_id, {}).get("normalized_score", 0)
            
            # 加权融合
            fused_score = (
                self.vector_weight * vector_norm +
                self.bm25_weight * bm25_norm
            )
            
            # 获取文档内容
            doc = vector_docs.get(doc_id) or bm25_docs.get(doc_id)
            
            fused_results.append({
                "id": doc_id,
                "content": doc.get("content", ""),
                "metadata": doc.get("metadata", {}),
                "vector_score": vector_score,
                "bm25_score": bm25_score,
                "fused_score": fused_score
            })
        
        # 按融合分数排序
        fused_results.sort(key=lambda x: x["fused_score"], reverse=True)
        
        return fused_results
    
    def _calculate_normalized_scores(
        self,
        results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """计算归一化分数"""
        if not results:
            return results
        
        scores = [r.get("score", 0) for r in results]
        normalized_scores = self._normalize_scores(scores)
        
        for i, result in enumerate(results):
            result["normalized_score"] = normalized_scores[i]
        
        return results
    
    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """执行混合检索"""
        if top_k is None:
            top_k = self.rerank_top_k
        
        # 根据检索模式选择不同的检索策略
        if self.retrieval_mode == "vector_only":
            return self._vector_only_retrieve(query, top_k)
        elif self.retrieval_mode == "bm25_only":
            return self._bm25_only_retrieve(query, top_k)
        elif self.retrieval_mode == "hybrid":
            return self._hybrid_no_rerank(query, top_k)
        else:  # hybrid_rerank
            return self._hybrid_with_rerank(query, top_k)
    
    def _vector_only_retrieve(
        self,
        query: str,
        top_k: int
    ) -> List[Dict[str, Any]]:
        """仅向量检索"""
        results = self.vector_retriever.search(query, top_k * self.candidate_multiplier)
        
        # 归一化分数
        results = self._calculate_normalized_scores(results)
        
        # 重排序
        results = self.reranker.rerank(query, results, top_k)
        
        return results
    
    def _bm25_only_retrieve(
        self,
        query: str,
        top_k: int
    ) -> List[Dict[str, Any]]:
        """仅BM25检索"""
        results = self.bm25_retriever.search(query, top_k * self.candidate_multiplier)
        
        # 归一化分数
        results = self._calculate_normalized_scores(results)
        
        # 重排序
        results = self.reranker.rerank(query, results, top_k)
        
        return results
    
    def _hybrid_no_rerank(
        self,
        query: str,
        top_k: int
    ) -> List[Dict[str, Any]]:
        """混合检索（无重排序）"""
        # 向量检索
        vector_results = self.vector_retriever.search(
            query, top_k * self.candidate_multiplier
        )
        vector_results = self._calculate_normalized_scores(vector_results)
        
        # BM25检索
        bm25_results = self.bm25_retriever.search(
            query, top_k * self.candidate_multiplier
        )
        bm25_results = self._calculate_normalized_scores(bm25_results)
        
        # 融合结果
        fused_results = self._fuse_scores(vector_results, bm25_results)
        
        # 返回Top-K
        return fused_results[:top_k]
    
    def _hybrid_with_rerank(
        self,
        query: str,
        top_k: int
    ) -> List[Dict[str, Any]]:
        """混合检索（带重排序）"""
        # 向量检索
        vector_results = self.vector_retriever.search(
            query, top_k * self.candidate_multiplier
        )
        vector_results = self._calculate_normalized_scores(vector_results)
        
        # BM25检索
        bm25_results = self.bm25_retriever.search(
            query, top_k * self.candidate_multiplier
        )
        bm25_results = self._calculate_normalized_scores(bm25_results)
        
        # 融合结果
        fused_results = self._fuse_scores(vector_results, bm25_results)
        
        # 重排序
        reranked_results = self.reranker.rerank(
            query, fused_results, top_k
        )
        
        return reranked_results
    
    def add_documents(self, documents: List[Dict[str, Any]]) -> bool:
        """添加文档到索引"""
        # 添加到向量索引
        self.vector_retriever.add_documents(documents)
        
        # 添加到BM25索引
        self.bm25_retriever.add_documents(documents)
        
        return True
    
    def get_status(self) -> Dict[str, Any]:
        """获取检索器状态"""
        return {
            "retrieval_mode": self.retrieval_mode,
            "vector_weight": self.vector_weight,
            "bm25_weight": self.bm25_weight,
            "candidate_multiplier": self.candidate_multiplier,
            "rerank_top_k": self.rerank_top_k,
            "vector_retriever_status": self.vector_retriever.get_status(),
            "bm25_retriever_status": self.bm25_retriever.get_index_info(),
            "reranker_status": self.reranker.get_status()
        }