# src/rag/bm25_retriever.py
"""BM25关键词检索器"""
from typing import Dict, Any, List, Optional
import json
import os
import math
from pathlib import Path
from collections import defaultdict
import jieba

from src.config.rag_config import RAGConfigManager


class BM25Retriever:
    """BM25关键词检索器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化BM25检索器"""
        self.config = config or RAGConfigManager.get_bm25_config()
        self.index_path = Path(self.config.get("index_path", "data/bm25_index"))
        self.index_file = self.config.get("index_file", "bm25_index.json")
        
        # BM25参数
        self.k1 = self.config.get("k1", 1.5)
        self.b = self.config.get("b", 0.75)
        
        # 检索参数
        self.top_k = self.config.get("top_k", 10)
        
        # 索引数据
        self.index: Dict[str, Any] = {
            "documents": [],  # 文档列表
            "doc_lengths": [],  # 文档长度
            "doc_freqs": defaultdict(int),  # 文档频率
            "term_freqs": [],  # 词频
            "avg_doc_length": 0,
            "total_docs": 0
        }
        
        # 加载索引
        self._load_index()
    
    def _load_index(self) -> bool:
        """加载BM25索引"""
        try:
            index_file = self.index_path / self.index_file
            if index_file.exists():
                with open(index_file, 'r', encoding='utf-8') as f:
                    self.index = json.load(f)
                return True
        except Exception as e:
            print(f"Error loading BM25 index: {e}")
        return False
    
    def _save_index(self) -> bool:
        """保存BM25索引"""
        try:
            self.index_path.mkdir(parents=True, exist_ok=True)
            index_file = self.index_path / self.index_file
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(self.index, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Error saving BM25 index: {e}")
            return False
    
    def _tokenize(self, text: str) -> List[str]:
        """中文分词"""
        return list(jieba.cut(text))
    
    def _calculate_doc_length(self, tokens: List[str]) -> int:
        """计算文档长度"""
        return len(tokens)
    
    def _calculate_idf(self, term: str) -> float:
        """计算IDF值"""
        doc_freq = self.index["doc_freqs"].get(term, 0)
        total_docs = self.index["total_docs"]
        
        if doc_freq == 0:
            return 0
        
        # BM25 IDF公式
        return math.log((total_docs - doc_freq + 0.5) / (doc_freq + 0.5) + 1)
    
    def _calculate_bm25_score(
        self,
        query_tokens: List[str],
        doc_idx: int
    ) -> float:
        """计算BM25分数"""
        score = 0
        doc_length = self.index["doc_lengths"][doc_idx]
        avg_doc_length = self.index["avg_doc_length"]
        term_freqs = self.index["term_freqs"][doc_idx]
        
        for term in query_tokens:
            if term not in term_freqs:
                continue
            
            tf = term_freqs[term]
            idf = self._calculate_idf(term)
            
            # BM25分数公式
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * doc_length / avg_doc_length)
            
            score += idf * (numerator / denominator)
        
        return score
    
    def add_documents(self, documents: List[Dict[str, Any]]) -> bool:
        """添加文档到索引"""
        try:
            for doc in documents:
                content = doc.get("content", "")
                doc_id = doc.get("id", len(self.index["documents"]))
                metadata = doc.get("metadata", {})
                
                # 分词
                tokens = self._tokenize(content)
                doc_length = self._calculate_doc_length(tokens)
                
                # 计算词频
                term_freqs = defaultdict(int)
                for token in tokens:
                    term_freqs[token] += 1
                
                # 更新索引
                self.index["documents"].append({
                    "id": doc_id,
                    "content": content,
                    "metadata": metadata
                })
                self.index["doc_lengths"].append(doc_length)
                self.index["term_freqs"].append(dict(term_freqs))
                
                # 更新文档频率
                unique_terms = set(tokens)
                for term in unique_terms:
                    self.index["doc_freqs"][term] += 1
            
            # 更新统计信息
            self.index["total_docs"] = len(self.index["documents"])
            if self.index["total_docs"] > 0:
                self.index["avg_doc_length"] = sum(self.index["doc_lengths"]) / self.index["total_docs"]
            
            # 保存索引
            self._save_index()
            
            return True
        except Exception as e:
            print(f"Error adding documents: {e}")
            return False
    
    def search(self, query: str, top_k: Optional[int] = None) -> List[Dict[str, Any]]:
        """搜索文档"""
        if top_k is None:
            top_k = self.top_k
        
        # 分词
        query_tokens = self._tokenize(query)
        
        if not query_tokens:
            return []
        
        # 计算所有文档的分数
        scores = []
        for doc_idx in range(self.index["total_docs"]):
            score = self._calculate_bm25_score(query_tokens, doc_idx)
            scores.append((doc_idx, score))
        
        # 排序
        scores.sort(key=lambda x: x[1], reverse=True)
        
        # 返回Top-K结果
        results = []
        for doc_idx, score in scores[:top_k]:
            doc = self.index["documents"][doc_idx]
            results.append({
                "id": doc["id"],
                "content": doc["content"],
                "metadata": doc.get("metadata", {}),
                "score": score
            })
        
        return results
    
    def search_with_filter(
        self,
        query: str,
        filter_fn: Optional[callable] = None,
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """带过滤条件的搜索"""
        results = self.search(query, top_k)
        
        if filter_fn:
            results = [r for r in results if filter_fn(r)]
        
        return results
    
    def update_document(self, doc_id: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """更新文档"""
        try:
            # 找到文档索引
            for i, doc in enumerate(self.index["documents"]):
                if doc["id"] == doc_id:
                    # 重新分词
                    tokens = self._tokenize(content)
                    doc_length = self._calculate_doc_length(tokens)
                    term_freqs = defaultdict(int)
                    for token in tokens:
                        term_freqs[token] += 1
                    
                    # 更新文档
                    self.index["documents"][i]["content"] = content
                    self.index["documents"][i]["metadata"] = metadata or {}
                    self.index["doc_lengths"][i] = doc_length
                    self.index["term_freqs"][i] = dict(term_freqs)
                    
                    # 更新文档频率
                    for term, freq in self.index["doc_freqs"].items():
                        if term in term_freqs:
                            self.index["doc_freqs"][term] = freq  # 简化处理
                    break
            
            # 保存索引
            self._save_index()
            
            return True
        except Exception as e:
            print(f"Error updating document: {e}")
            return False
    
    def delete_document(self, doc_id: str) -> bool:
        """删除文档"""
        try:
            # 找到文档索引
            for i, doc in enumerate(self.index["documents"]):
                if doc["id"] == doc_id:
                    # 删除文档
                    self.index["documents"].pop(i)
                    self.index["doc_lengths"].pop(i)
                    self.index["term_freqs"].pop(i)
                    
                    # 更新统计信息
                    self.index["total_docs"] = len(self.index["documents"])
                    if self.index["total_docs"] > 0:
                        self.index["avg_doc_length"] = sum(self.index["doc_lengths"]) / self.index["total_docs"]
                    break
            
            # 保存索引
            self._save_index()
            
            return True
        except Exception as e:
            print(f"Error deleting document: {e}")
            return False
    
    def clear_index(self) -> bool:
        """清空索引"""
        try:
            self.index = {
                "documents": [],
                "doc_lengths": [],
                "doc_freqs": defaultdict(int),
                "term_freqs": [],
                "avg_doc_length": 0,
                "total_docs": 0
            }
            self._save_index()
            return True
        except Exception as e:
            print(f"Error clearing index: {e}")
            return False
    
    def get_index_info(self) -> Dict[str, Any]:
        """获取索引信息"""
        return {
            "total_docs": self.index["total_docs"],
            "avg_doc_length": self.index["avg_doc_length"],
            "vocab_size": len(self.index["doc_freqs"]),
            "index_path": str(self.index_path)
        }