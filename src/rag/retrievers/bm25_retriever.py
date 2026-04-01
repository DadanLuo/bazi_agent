"""
==============================================================================
BM25 检索器
==============================================================================

功能说明：
    本模块实现了基于 BM25 算法的关键词检索器，用于从知识库中检索关键词
    精确匹配的文档。

核心功能：
    - BM25 检索：使用 BM25 算法进行关键词检索
    - 词频统计：计算文档的词频
    - IDF 计算：计算逆文档频率

==============================================================================
"""

import logging
import math
import re
from typing import List, Dict, Any, Optional
from collections import defaultdict

from src.rag.agentic.state import Document

logger = logging.getLogger(__name__)


class BM25Retriever:
    """
    ==============================================================================
    BM25 检索器
    ==============================================================================
    
    功能说明：
        基于 BM25 算法的关键词检索器，用于从知识库中检索关键词精确匹配的文档。
    
    核心方法：
        - search(): BM25 检索
    
    BM25 公式：
        score(Q, D) = sum[ IDF(q_i) * f(q_i, D) * (k1 + 1) / 
             (f(q_i, D) + k1 * (1 - b + b * |D| / avgdl)) ]
    
    ==============================================================================
    """

    def __init__(self, documents: List[Document] = None):
        """
        ==============================================================================
        初始化 BM25 检索器
        ==============================================================================
        
        参数说明：
            documents: 文档列表
        
        ==============================================================================
        """
        self.documents: List[Document] = documents or []
        self.doc_freq: Dict[str, int] = defaultdict(int)  # 文档频率
        self.term_freq: List[Dict[str, int]] = []  # 词频
        self.doc_lengths: List[int] = []  # 文档长度
        self.avgdl = 0.0  # 平均文档长度
        self.n = 0  # 文档数量
        
        # BM25 参数
        self.k1 = 1.5
        self.b = 0.75
        
        if self.documents:
            self._build_index()
        
        logger.info("BM25Retriever 初始化完成")

    def _build_index(self):
        """构建倒排索引"""
        logger.info("构建 BM25 索引")
        
        self.n = len(self.documents)
        self.term_freq = []
        self.doc_lengths = []
        
        # 统计文档频率
        for doc in self.documents:
            terms = self._tokenize(doc.content)
            term_count = defaultdict(int)
            
            for term in terms:
                term_count[term] += 1
                self.doc_freq[term] += 1
            
            self.term_freq.append(dict(term_count))
            self.doc_lengths.append(len(terms))
        
        # 计算平均文档长度
        if self.doc_lengths:
            self.avgdl = sum(self.doc_lengths) / len(self.doc_lengths)
        
        logger.info(f"索引构建完成，文档数量: {self.n}")

    def _tokenize(self, text: str) -> List[str]:
        """
        ==============================================================================
        分词
        ==============================================================================
        
        功能说明：
            将文本分词为关键词列表。
        
        参数说明：
            text: 文本
        
        返回值：
            List[str]: 词列表
        
        ==============================================================================
        """
        # 简单分词：按空格和标点分割
        text = text.lower()
        terms = re.findall(r'\w+', text)
        
        # 移除停用词
        stopwords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'must', 'shall', 'can', 'need', 'dare',
            'ought', 'used', 'it', 'its', 'this', 'that', 'these', 'those',
            'i', 'you', 'he', 'she', 'we', 'they', 'what', 'which', 'who',
            'whom', 'whose', 'where', 'when', 'why', 'how', 'all', 'each',
            'every', 'both', 'few', 'more', 'most', 'other', 'some', 'such',
            'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too',
            'very', 's', 't', 'can', 'don', 'just', 'don', 'll', 're', 've'
        }
        
        return [term for term in terms if term not in stopwords and len(term) > 1]

    def search(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.5,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """
        ==============================================================================
        BM25 检索
        ==============================================================================
        
        功能说明：
            使用 BM25 算法检索相关文档。
        
        参数说明：
            query: 用户查询文本
            top_k: 返回的文档数量
            threshold: 相似度阈值
            filter: 元数据过滤器
        
        返回值：
            List[Document]: 检索到的文档列表
        
        ==============================================================================
        """
        logger.info(f"开始 BM25 检索: {query}")
        
        if not self.documents:
            logger.warning("没有索引文档")
            return []
        
        # 分词查询
        query_terms = self._tokenize(query)
        
        if not query_terms:
            logger.warning("查询分词为空")
            return []
        
        # 计算 IDF
        idf = {}
        for term in query_terms:
            df = self.doc_freq.get(term, 0)
            idf[term] = math.log((self.n - df + 0.5) / (df + 0.5) + 1)
        
        # 计算每个文档的分数
        scores = []
        for i, doc in enumerate(self.documents):
            if filter and not self._match_filter(doc, filter):
                continue
            
            score = self._compute_score(query_terms, i, idf)
            if score >= threshold:
                scores.append((i, score))
        
        # 排序并返回
        scores.sort(key=lambda x: x[1], reverse=True)
        
        docs = []
        for i, score in scores[:top_k]:
            docs.append(Document(
                content=self.documents[i].content,
                metadata=self.documents[i].metadata,
                score=score,
                source_type="bm25"
            ))
        
        logger.info(f"BM25 检索完成，返回 {len(docs)} 个文档")
        return docs

    def _match_filter(self, doc: Document, filter: Dict[str, Any]) -> bool:
        """
        ==============================================================================
        匹配过滤器
        ==============================================================================
        
        功能说明：
            检查文档是否匹配过滤器条件。
        
        参数说明：
            doc: 文档
            filter: 过滤器
        
        返回值：
            bool: 是否匹配
        
        ==============================================================================
        """
        for key, value in filter.items():
            if key in doc.metadata:
                if isinstance(value, list):
                    if doc.metadata[key] not in value:
                        return False
                elif doc.metadata[key] != value:
                    return False
        return True

    def _compute_score(
        self,
        query_terms: List[str],
        doc_idx: int,
        idf: Dict[str, float]
    ) -> float:
        """
        ==============================================================================
        计算 BM25 分数
        ==============================================================================
        
        功能说明：
            计算文档与查询的 BM25 相似度分数。
        
        参数说明：
            query_terms: 查询词列表
            doc_idx: 文档索引
            idf: IDF 字典
        
        返回值：
            float: BM25 分数
        
        ==============================================================================
        """
        score = 0.0
        doc_length = self.doc_lengths[doc_idx]
        
        for term in query_terms:
            if term not in self.term_freq[doc_idx]:
                continue
            
            f = self.term_freq[doc_idx][term]
            idf_term = idf.get(term, 0)
            
            # BM25 公式
            numerator = f * (self.k1 + 1)
            denominator = f + self.k1 * (1 - self.b + self.b * doc_length / self.avgdl)
            
            score += idf_term * numerator / denominator
        
        return score

    def add_documents(self, documents: List[Document]):
        """
        ==============================================================================
        添加文档
        ==============================================================================
        
        功能说明：
            添加新文档到索引。
        
        参数说明：
            documents: 文档列表
        
        ==============================================================================
        """
        self.documents.extend(documents)
        self._build_index()
        logger.info(f"添加 {len(documents)} 个文档")

    def remove_documents(self, indices: List[int]):
        """
        ==============================================================================
        删除文档
        ==============================================================================
        
        功能说明：
            从索引中删除文档。
        
        参数说明：
            indices: 文档索引列表
        
        ==============================================================================
        """
        # 按索引删除（从大到小排序以避免索引错误）
        for i in sorted(indices, reverse=True):
            if 0 <= i < len(self.documents):
                self.documents.pop(i)
        
        self._build_index()
        logger.info(f"删除 {len(indices)} 个文档")
