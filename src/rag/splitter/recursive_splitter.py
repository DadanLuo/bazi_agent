"""
递归文本切分器
用于处理八字命理文档的智能递归切分，保留章节结构和上下文信息
"""
import re
from typing import List, Dict, Optional
from dataclasses import dataclass

from src.rag.metadata_extractor import extract_metadata


@dataclass
class Chunk:
    """文本块数据类"""
    content: str
    metadata: Dict
    chunk_id: str = ""
    parent_id: Optional[str] = None
    level: int = 0  # 切分层级，0为原始文档，1为一级切分，以此类推


class RecursiveTextSplitter:
    """
    递归文本切分器
    
    功能特点：
    1. 按照文档结构层次进行递归切分（章节 -> 段落 -> 句子）
    2. 保留完整的元数据信息，包括章节名、话题、关键字等
    3. 支持重叠以保持上下文连贯性
    4. 自动识别和处理八字命理文档的特殊结构
    """

    LARGE_TEXT_THRESHOLD_MULTIPLIER = 32
    
    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        separators: Optional[List[str]] = None,
        keep_separator: bool = True
    ):
        """
        初始化递归切分器
        
        Args:
            chunk_size: 目标chunk大小（字符数）
            chunk_overlap: chunk之间的重叠大小
            separators: 分隔符列表，按优先级排序
            keep_separator: 是否在结果中保留分隔符
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.keep_separator = keep_separator
        
        # 默认分隔符，按优先级从高到低
        if separators is None:
            self.separators = [
                "\n\n",  # 章节分隔
                "\n",    # 段落分隔  
                "。",    # 句号
                "；",    # 分号
                "，",    # 逗号
                "",      # 字符级别（最后手段）
            ]
        else:
            self.separators = separators
            
    def split_text(self, text: str, source: str = "", chapter_info: Dict = None, max_depth: int = 10) -> List[Chunk]:
        """
        递归切分文本
        
        Args:
            text: 要切分的文本
            source: 文档来源
            chapter_info: 章节信息，包含章节名、父章节等
            max_depth: 最大递归深度，防止无限递归
            
        Returns:
            切分后的Chunk列表
        """
        if not text.strip():
            return []
            
        # 如果文本长度小于chunk_size，直接作为一个chunk
        if len(text) <= self.chunk_size:
            metadata = self._create_metadata(text, source, chapter_info)
            return [Chunk(content=text.strip(), metadata=metadata)]

        # 超大文本直接走线性快速切分，避免深递归导致长时间卡住
        if len(text) >= self.chunk_size * self.LARGE_TEXT_THRESHOLD_MULTIPLIER:
            return self._split_large_text(text, source, chapter_info)
            
        # 检查递归深度
        if max_depth <= 0:
            # 达到最大深度，强制字符级别切分
            return self._split_by_chars(text, source, chapter_info)
            
        # 尝试使用分隔符进行切分
        for separator in self.separators:
            if separator == "":
                # 字符级别切分（最后手段）
                return self._split_by_chars(text, source, chapter_info)
                
            if separator in text:
                chunks = self._split_with_separator(text, separator, source, chapter_info, max_depth)
                if chunks:
                    return chunks
                    
        # 如果所有分隔符都失败，使用字符级别切分
        return self._split_by_chars(text, source, chapter_info)

    def _split_large_text(
        self,
        text: str,
        source: str,
        chapter_info: Dict,
    ) -> List[Chunk]:
        """超大文本快速切分：尽量保留高层边界，避免深递归。"""
        for separator in self.separators:
            if separator and separator in text:
                segments = text.split(separator)
                if self.keep_separator:
                    rebuilt_segments = []
                    for i, segment in enumerate(segments):
                        if i < len(segments) - 1:
                            rebuilt_segments.append(segment + separator)
                        else:
                            rebuilt_segments.append(segment)
                    segments = rebuilt_segments
                return self._pack_segments(segments, source, chapter_info)

        return self._split_by_chars(text, source, chapter_info)

    def _pack_segments(
        self,
        segments: List[str],
        source: str,
        chapter_info: Dict,
    ) -> List[Chunk]:
        """将片段线性打包到接近 chunk_size，超长片段再退化为字符切分。"""
        chunks = []
        current_parts = []
        current_length = 0

        def flush_current_parts() -> None:
            nonlocal current_parts, current_length
            if not current_parts:
                return

            merged_text = "".join(current_parts).strip()
            if merged_text:
                metadata = self._create_metadata(merged_text, source, chapter_info)
                chunks.append(Chunk(content=merged_text, metadata=metadata))

            current_parts = []
            current_length = 0

        for segment in segments:
            segment = segment.strip()
            if not segment:
                continue

            if len(segment) > self.chunk_size:
                flush_current_parts()
                chunks.extend(self._split_by_chars(segment, source, chapter_info))
                continue

            if current_parts and current_length + len(segment) > self.chunk_size:
                flush_current_parts()

            current_parts.append(segment)
            current_length += len(segment)

        flush_current_parts()
        return self._merge_small_chunks(chunks)
        
    def _split_with_separator(
        self, 
        text: str, 
        separator: str, 
        source: str, 
        chapter_info: Dict,
        max_depth: int
    ) -> List[Chunk]:
        """使用指定分隔符进行切分"""
        if separator not in text:
            return []
            
        # 分割文本
        splits = text.split(separator)
        
        # 如果不分隔符，返回空
        if len(splits) <= 1:
            return []
            
        # 重构分割结果，考虑是否保留分隔符
        if self.keep_separator and separator != "":
            # 在每个分割后添加分隔符（除了最后一个）
            splits_with_sep = []
            for i, split in enumerate(splits):
                if i < len(splits) - 1:
                    splits_with_sep.append(split + separator)
                else:
                    splits_with_sep.append(split)
            splits = splits_with_sep
            
        # 过滤空字符串
        splits = [s for s in splits if s.strip()]
        
        if not splits:
            return []
            
        chunks = []
        current_parts = []
        current_length = 0

        def flush_current_parts() -> None:
            nonlocal current_parts, current_length
            if not current_parts:
                return

            merged_text = "".join(current_parts).strip()
            if merged_text:
                metadata = self._create_metadata(merged_text, source, chapter_info)
                chunks.append(Chunk(content=merged_text, metadata=metadata))

            current_parts = []
            current_length = 0

        for split in splits:
            split = split.strip()
            if not split:
                continue

            if len(split) > self.chunk_size:
                flush_current_parts()
                # 递归切分，减少最大深度
                recursive_chunks = self.split_text(split, source, chapter_info, max_depth - 1)
                chunks.extend(recursive_chunks)
                continue

            if current_parts and current_length + len(split) > self.chunk_size:
                flush_current_parts()

            current_parts.append(split)
            current_length += len(split)

        flush_current_parts()
                
        return self._merge_small_chunks(chunks)
        
    def _split_by_chars(
        self, 
        text: str, 
        source: str, 
        chapter_info: Dict
    ) -> List[Chunk]:
        """按字符进行切分（最后手段）"""
        chunks = []
        start = 0
        shared_metadata = None

        if len(text) > self.chunk_size * 2:
            shared_metadata = self._create_metadata(text, source, chapter_info)
        
        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            chunk_text = text[start:end]
            
            if chunk_text.strip():
                if shared_metadata is not None:
                    metadata = shared_metadata.copy()
                    metadata.update({
                        "chunk_length": len(chunk_text),
                        "has_context": len(chunk_text) > self.chunk_size // 2,
                    })
                else:
                    metadata = self._create_metadata(chunk_text, source, chapter_info)
                chunks.append(Chunk(content=chunk_text.strip(), metadata=metadata))

            if end >= len(text):
                break

            next_start = max(0, end - self.chunk_overlap)
            if next_start <= start:
                break
            start = next_start
                
        return chunks
        
    def _merge_small_chunks(self, chunks: List[Chunk]) -> List[Chunk]:
        """合并过小的chunks以避免碎片化"""
        if len(chunks) <= 1:
            return chunks
            
        merged_chunks = []
        current_chunk = chunks[0]
        
        for next_chunk in chunks[1:]:
            # 如果当前chunk太小，尝试合并
            if (len(current_chunk.content) < self.chunk_size // 2 and 
                len(current_chunk.content) + len(next_chunk.content) <= self.chunk_size):
                # 合并内容
                merged_content = current_chunk.content + " " + next_chunk.content
                # 合并元数据（优先保留更丰富的元数据）
                merged_metadata = self._merge_metadata(current_chunk.metadata, next_chunk.metadata)
                current_chunk = Chunk(
                    content=merged_content,
                    metadata=merged_metadata
                )
            else:
                merged_chunks.append(current_chunk)
                current_chunk = next_chunk
                
        merged_chunks.append(current_chunk)
        return merged_chunks
        
    def _merge_metadata(self, meta1: Dict, meta2: Dict) -> Dict:
        """合并两个元数据字典"""
        merged = meta1.copy()
        
        # 合并关键词列表
        if "keywords" in meta1 and "keywords" in meta2:
            merged["keywords"] = list(set(meta1["keywords"] + meta2["keywords"]))
            
        # 合并实体标签
        entity_fields = ["wuxing", "tiangan", "dizhi", "shensha", "geju", "yongshen", "liunian", "changsheng"]
        for field in entity_fields:
            if field in meta1 and field in meta2:
                merged[field] = list(set(meta1[field] + meta2[field]))
                
        # 主题选择更具体的
        if meta1.get("topic") != "general" or meta2.get("topic") != "general":
            if meta1.get("topic") != "general":
                merged["topic"] = meta1["topic"]
                merged["sub_topic"] = meta1.get("sub_topic", "general")
            else:
                merged["topic"] = meta2["topic"]
                merged["sub_topic"] = meta2.get("sub_topic", "general")
                
        return merged
        
    def _create_metadata(self, text: str, source: str, chapter_info: Dict = None) -> Dict:
        """创建chunk的元数据"""
        # 基础元数据提取
        chapter_name = chapter_info.get("chapter_name", "") if chapter_info else ""
        section_path = chapter_info.get("section_path", "") if chapter_info else ""
        metadata = extract_metadata(text, source, "", chapter_name, section_path)
        
        # 添加切分相关信息
        metadata.update({
            "chunk_length": len(text),
            "chunk_type": self._classify_chunk_type(text, metadata),
            "has_context": len(text) > self.chunk_size // 2  # 是否有足够的上下文
        })
        
        return metadata
        
    def _classify_chunk_type(self, text: str, metadata: Dict) -> str:
        """分类chunk类型，考虑元数据信息"""
        # 如果已经有chunk_type，直接使用
        if metadata.get("chunk_type") and metadata["chunk_type"] != "general":
            return metadata["chunk_type"]
            
        # 基于内容和元数据进行分类
        if metadata.get("topic") and metadata["topic"] != "general":
            return f"{metadata['topic']}_chunk"
            
        if any(keyword in text for keyword in ["理论", "原理", "概念", "定义"]):
            return "theory"
        elif any(keyword in text for keyword in ["规则", "方法", "步骤", "条件"]):
            return "rule"
        elif any(keyword in text for keyword in ["案例", "实例", "例子", "分析"]):
            return "case"
        elif any(keyword in text for keyword in ["示例", "举例", "说明"]):
            return "example"
        else:
            return "general"


# 全局实例
recursive_splitter = RecursiveTextSplitter()


def split_document_recursive(text: str, source: str = "", chapter_info: Dict = None) -> List[Dict]:
    """
    便捷函数：递归切分文档
    
    Args:
        text: 文档文本
        source: 文档来源
        chapter_info: 章节信息
        
    Returns:
        切分后的chunks列表，每个chunk包含content和metadata
    """
    chunks = recursive_splitter.split_text(text, source, chapter_info)
    return [{"content": chunk.content, "metadata": chunk.metadata} for chunk in chunks]
