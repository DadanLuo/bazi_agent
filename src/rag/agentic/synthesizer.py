"""
==============================================================================
知识整合器
==============================================================================

功能说明：
    本模块实现了知识整合器，用于整合多源检索结果，消除冲突，生成结构化的
    知识上下文。

核心功能：
    - 去重：消除重复内容
    - 冲突检测：识别矛盾信息
    - 冲突解决：根据来源可信度选择
    - 结构化：按逻辑组织内容

==============================================================================
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from .state import Document

logger = logging.getLogger(__name__)


@dataclass
class Conflict:
    """
    ==============================================================================
    冲突数据模型
    ==============================================================================
    
    功能说明：
        表示两个文档之间的冲突。
    
    属性：
        doc1: 第一个文档
        doc2: 第二个文档
        conflict_type: 冲突类型
        description: 冲突描述
    
    ==============================================================================
    """
    doc1: Document
    doc2: Document
    conflict_type: str = "content"
    description: str = ""


class KnowledgeSynthesizer:
    """
    ==============================================================================
    知识整合器
    ==============================================================================
    
    功能说明：
        整合多源检索结果，消除冲突，生成结构化的知识上下文。
    
    核心方法：
        - synthesize(): 整合多源知识
    
    处理步骤：
        1. 去重：消除重复内容
        2. 冲突检测：识别矛盾信息
        3. 冲突解决：根据来源可信度选择
        4. 结构化：按逻辑组织内容
    
    ==============================================================================
    """

    # 来源可信度权重
    SOURCE_WEIGHTS = {
        "vector": 1.0,
        "bm25": 0.9,
        "graph": 1.1,  # 图谱通常更可靠
        "web": 0.7
    }

    def __init__(self):
        """初始化知识整合器"""
        logger.info("KnowledgeSynthesizer 初始化完成")

    def synthesize(
        self,
        query: str,
        docs: List[Document],
        sources: List[str]
    ) -> str:
        """
        ==============================================================================
        整合多源知识
        ==============================================================================
        
        功能说明：
            整合多源检索结果，生成结构化的知识上下文。
        
        参数说明：
            query: 用户查询文本
            docs: 检索到的文档列表
            sources: 使用的知识源列表
        
        返回值：
            str: 整合后的知识上下文
        
        处理流程：
            1. 去重
            2. 冲突检测
            3. 冲突解决
            4. 结构化整合
        
        ==============================================================================
        """
        logger.info(f"开始整合知识，文档数量: {len(docs)}")
        
        # 1. 去重
        unique_docs = self._deduplicate(docs)
        logger.info(f"去重后文档数量: {len(unique_docs)}")
        
        # 2. 冲突检测
        conflicts = self._detect_conflicts(unique_docs)
        logger.info(f"检测到冲突数量: {len(conflicts)}")
        
        # 3. 冲突解决
        resolved_docs = self._resolve_conflicts(unique_docs, conflicts)
        logger.info(f"冲突解决后文档数量: {len(resolved_docs)}")
        
        # 4. 结构化整合
        context = self._structure_knowledge(query, resolved_docs, sources)
        
        return context

    def _deduplicate(self, docs: List[Document]) -> List[Document]:
        """
        ==============================================================================
        去重
        ==============================================================================
        
        功能说明：
            基于内容相似度，消除重复文档。
        
        参数说明：
            docs: 检索到的文档列表
        
        返回值：
            List[Document]: 去重后的文档列表
        
        ==============================================================================
        """
        seen = set()
        unique = []
        
        for doc in docs:
            # 使用内容的前100个字符作为哈希键
            content_hash = hash(doc.content[:100])
            
            if content_hash not in seen:
                seen.add(content_hash)
                unique.append(doc)
        
        return unique

    def _detect_conflicts(self, docs: List[Document]) -> List[Conflict]:
        """
        ==============================================================================
        冲突检测
        ==============================================================================
        
        功能说明：
            识别文档之间的矛盾信息。
        
        参数说明：
            docs: 检索到的文档列表
        
        返回值：
            List[Conflict]: 冲突列表
        
        ==============================================================================
        """
        conflicts = []
        
        for i, doc1 in enumerate(docs):
            for doc2 in docs[i+1:]:
                if self._is_conflict(doc1, doc2):
                    conflicts.append(Conflict(doc1, doc2))
        
        return conflicts

    def _is_conflict(self, doc1: Document, doc2: Document) -> bool:
        """
        ==============================================================================
        判断两个文档是否存在冲突
        ==============================================================================
        
        功能说明：
            判断两个文档是否包含矛盾信息。
        
        参数说明：
            doc1: 第一个文档
            doc2: 第二个文档
        
        返回值：
            bool: 是否存在冲突
        
        ==============================================================================
        """
        content1 = doc1.content.lower()
        content2 = doc2.content.lower()
        
        # 简单冲突检测：内容完全相反
        opposite_patterns = [
            ("是", "不是"),
            ("有", "没有"),
            ("好", "坏"),
            ("正确", "错误"),
            ("真", "假")
        ]
        
        for pattern1, pattern2 in opposite_patterns:
            if pattern1 in content1 and pattern2 in content2:
                return True
            if pattern2 in content1 and pattern1 in content2:
                return True
        
        return False

    def _resolve_conflicts(
        self,
        docs: List[Document],
        conflicts: List[Conflict]
    ) -> List[Document]:
        """
        ==============================================================================
        冲突解决
        ==============================================================================
        
        功能说明：
            根据来源可信度，解决文档冲突。
        
        参数说明：
            docs: 检索到的文档列表
            conflicts: 冲突列表
        
        返回值：
            List[Document]: 冲突解决后的文档列表
        
        ==============================================================================
        """
        resolved = list(docs)
        
        for conflict in conflicts:
            # 选择可信度更高的来源
            winner = self._select_reliable(conflict.doc1, conflict.doc2)
            loser = conflict.doc2 if winner == conflict.doc1 else conflict.doc1
            
            if loser in resolved:
                resolved.remove(loser)
                logger.info(f"移除冲突文档: {loser.source}")
        
        return resolved

    def _select_reliable(self, doc1: Document, doc2: Document) -> Document:
        """
        ==============================================================================
        选择更可靠的文档
        ==============================================================================
        
        功能说明：
            根据来源可信度，选择更可靠的文档。
        
        参数说明：
            doc1: 第一个文档
            doc2: 第二个文档
        
        返回值：
            Document: 更可靠的文档
        
        ==============================================================================
        """
        weight1 = self.SOURCE_WEIGHTS.get(doc1.source_type, 1.0)
        weight2 = self.SOURCE_WEIGHTS.get(doc2.source_type, 1.0)
        
        # 考虑检索分数
        score1 = weight1 * doc1.score
        score2 = weight2 * doc2.score
        
        return doc1 if score1 >= score2 else doc2

    def _structure_knowledge(
        self,
        query: str,
        docs: List[Document],
        sources: List[str]
    ) -> str:
        """
        ==============================================================================
        结构化整合
        ==============================================================================
        
        功能说明：
            按逻辑组织知识内容，生成结构化的上下文。
        
        参数说明：
            query: 用户查询文本
            docs: 检索到的文档列表
            sources: 使用的知识源列表
        
        返回值：
            str: 结构化的知识上下文
        
        ==============================================================================
        """
        if not docs:
            return "未检索到相关知识。"
        
        # 按来源分组
        docs_by_source = {}
        for doc in docs:
            source = doc.source_type
            if source not in docs_by_source:
                docs_by_source[source] = []
            docs_by_source[source].append(doc)
        
        # 构建上下文
        context_parts = []
        
        # 添加来源信息
        context_parts.append("=== 检索来源 ===")
        context_parts.append(f"使用的知识源: {', '.join(sources)}")
        context_parts.append("")
        
        # 按来源组织内容
        for source_type in ["graph", "vector", "bm25"]:
            if source_type in docs_by_source:
                context_parts.append(f"=== {source_type.upper()} 检索结果 ===")
                for i, doc in enumerate(docs_by_source[source_type], 1):
                    context_parts.append(f"[{i}] 来源: {doc.source or '未知'}")
                    context_parts.append(f"    分数: {doc.score:.2f}")
                    context_parts.append(f"    内容: {doc.content[:200]}...")
                    context_parts.append("")
        
        # 如果有图谱结果，添加关系信息
        if "graph" in docs_by_source:
            context_parts.append("=== 图谱关系 ===")
            for doc in docs_by_source["graph"]:
                if "entities" in doc.metadata:
                    context_parts.append(f" 实体: {doc.metadata['entities']}")
            context_parts.append("")
        
        return "\n".join(context_parts)

    def synthesize_for_llm(
        self,
        query: str,
        docs: List[Document],
        sources: List[str]
    ) -> str:
        """
        ==============================================================================
        为 LLM 整合知识
        ==============================================================================
        
        功能说明：
            整合多源检索结果，生成适合 LLM 使用的上下文。
        
        参数说明：
            query: 用户查询文本
            docs: 检索到的文档列表
            sources: 使用的知识源列表
        
        返回值：
            str: 适合 LLM 使用的上下文
        
        ==============================================================================
        """
        if not docs:
            return "未检索到相关知识。"
        
        # 按相关性排序
        sorted_docs = sorted(docs, key=lambda d: d.score, reverse=True)
        
        # 构建上下文
        context_parts = []
        
        for i, doc in enumerate(sorted_docs[:5], 1):  # 只取前5个
            context_parts.append(f"[文档 {i}]")
            context_parts.append(f"来源: {doc.source_type}")
            context_parts.append(f"分数: {doc.score:.2f}")
            context_parts.append(f"内容: {doc.content}")
            context_parts.append("")
        
        return "\n".join(context_parts)
