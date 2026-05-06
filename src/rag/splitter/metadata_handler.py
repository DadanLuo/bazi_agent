"""
元数据处理器
用于在文档切分过程中处理和传递元数据信息
"""
import re
from typing import Dict, List, Optional
from pathlib import Path

from src.rag.metadata_extractor import extract_metadata
from src.rag.splitter.recursive_splitter import split_document_recursive


class MetadataHandler:
    """
    元数据处理器
    
    功能：
    1. 解析文档结构，提取章节信息
    2. 在递归切分过程中传递和更新元数据
    3. 确保元数据在各个环节正确保留
    """
    
    def __init__(self):
        # 章节标题模式（支持多级标题）
        self.chapter_patterns = [
            r'^(第[一二三四五六七八九十百千]+章)\s*(.+)$',  # 第一章 标题
            r'^([一二三四五六七八九十百千]+、)\s*(.+)$',     # 一、标题
            r'^(\d+\.\d+\.\d+)\s*(.+)$',                   # 1.1.1 标题
            r'^(\d+\.\d+)\s*(.+)$',                        # 1.1 标题  
            r'^(\d+)\s*(.+)$',                             # 1 标题
            r'^(#+)\s*(.+)$',                              # Markdown标题
        ]
        
    def extract_chapter_structure(self, text: str, source: str = "") -> List[Dict]:
        """
        提取文档的章节结构
        
        Args:
            text: 文档文本
            source: 文档来源
            
        Returns:
            章节信息列表，每个包含位置、标题、级别等信息
        """
        lines = text.split('\n')
        chapters = []
        current_path = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
                
            chapter_info = self._parse_chapter_line(line, i)
            if chapter_info:
                # 更新当前路径
                level = chapter_info['level']
                if level <= len(current_path):
                    current_path = current_path[:level-1]
                current_path.append(chapter_info['title'])
                
                chapter_info.update({
                    'source': source,
                    'path': '/'.join(current_path),
                    'full_path': current_path.copy()
                })
                chapters.append(chapter_info)
                
        return chapters
        
    def _parse_chapter_line(self, line: str, position: int) -> Optional[Dict]:
        """解析单行是否为章节标题"""
        for level, pattern in enumerate(self.chapter_patterns, 1):
            match = re.match(pattern, line)
            if match:
                if level <= 2:  # 前两种模式是中文章节
                    prefix = match.group(1)
                    title = match.group(2).strip()
                else:
                    prefix = match.group(1)
                    title = match.group(2).strip()
                    
                return {
                    'position': position,
                    'prefix': prefix,
                    'title': title,
                    'level': level,
                    'type': self._get_chapter_type(title)
                }
                
        return None
        
    def _get_chapter_type(self, title: str) -> str:
        """根据标题推断章节类型"""
        topic_keywords = {
            "格局": ["格局", "成格", "破格", "正官格", "财格", "印格", "食神格", "七杀格"],
            "用神": ["用神", "喜神", "忌神", "调候", "扶抑", "通关"],
            "五行": ["五行", "生克", "制化", "旺衰", "强弱"],
            "神煞": ["神煞", "贵人", "桃花", "驿马", "华盖", "文昌"],
            "流年": ["流年", "大运", "小运", "岁运", "太岁"],
            "十神": ["十神", "正官", "七杀", "正财", "偏财", "食神", "伤官", "比肩", "劫财", "正印", "偏印"],
            "长生": ["长生", "沐浴", "冠带", "临官", "帝旺", "衰", "病", "死", "墓", "绝", "胎", "养"],
        }
        
        for topic, keywords in topic_keywords.items():
            for keyword in keywords:
                if keyword in title:
                    return topic
                    
        return "general"
        
    def assign_chunks_to_chapters(self, chunks: List[Dict], chapters: List[Dict]) -> List[Dict]:
        """
        将chunks分配到对应的章节
        
        Args:
            chunks: 切分后的chunks列表
            chapters: 章节信息列表
            
        Returns:
            分配了章节信息的chunks列表
        """
        if not chapters:
            return chunks
            
        # 为每个chunk找到对应的章节
        assigned_chunks = []
        chapter_idx = 0
        
        for chunk in chunks:
            # 找到chunk对应的章节（基于位置或内容匹配）
            best_chapter = self._find_best_chapter_for_chunk(chunk, chapters, chapter_idx)
            if best_chapter:
                chunk['metadata'].update({
                    'chapter_name': best_chapter['title'],
                    'chapter_level': best_chapter['level'],
                    'chapter_type': best_chapter['type'],
                    'section_path': best_chapter.get('path', ''),
                    'source_chapter': best_chapter.get('source', '')
                })
                chapter_idx = chapters.index(best_chapter)
                
            assigned_chunks.append(chunk)
            
        return assigned_chunks
        
    def _find_best_chapter_for_chunk(self, chunk: Dict, chapters: List[Dict], start_idx: int) -> Optional[Dict]:
        """为chunk找到最合适的章节"""
        # 简单策略：使用最近的章节
        if start_idx < len(chapters):
            return chapters[start_idx]
        elif chapters:
            return chapters[-1]
        return None
        
    def enhance_metadata_with_context(self, metadata: Dict, context_chunks: List[Dict] = None) -> Dict:
        """
        使用上下文信息增强元数据
        
        Args:
            metadata: 原始元数据
            context_chunks: 上下文chunks（前一个和后一个chunk）
            
        Returns:
            增强后的元数据
        """
        enhanced = metadata.copy()
        
        # 如果有上下文chunks，合并关键词和实体
        if context_chunks:
            all_keywords = set(metadata.get('keywords', []))
            all_entities = {}
            
            entity_fields = ['wuxing', 'tiangan', 'dizhi', 'shensha', 'geju', 'yongshen', 'liunian', 'changsheng']
            
            for ctx_chunk in context_chunks:
                ctx_meta = ctx_chunk.get('metadata', {})
                all_keywords.update(ctx_meta.get('keywords', []))
                
                for field in entity_fields:
                    if field in ctx_meta:
                        if field not in all_entities:
                            all_entities[field] = set()
                        all_entities[field].update(ctx_meta[field])
                        
            enhanced['keywords'] = list(all_keywords)
            for field, entities in all_entities.items():
                enhanced[field] = list(entities)
                
        return enhanced


# 全局实例
metadata_handler = MetadataHandler()


def process_document_with_metadata(text: str, source: str = "") -> List[Dict]:
    """
    处理文档并保留完整的元数据信息
    
    Args:
        text: 文档文本
        source: 文档来源
        
    Returns:
        处理后的chunks列表，包含完整的元数据
    """
    # 1. 提取章节结构
    chapters = metadata_handler.extract_chapter_structure(text, source)
    
    # 2. 递归切分文档
    chunks = split_document_recursive(text, source)
    
    # 3. 分配章节信息到chunks
    assigned_chunks = metadata_handler.assign_chunks_to_chapters(chunks, chapters)
    
    return assigned_chunks