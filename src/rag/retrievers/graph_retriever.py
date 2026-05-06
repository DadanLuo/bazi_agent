"""
==============================================================================
图谱检索器
==============================================================================

功能说明：
    本模块实现了基于知识图谱的检索器，用于从知识图谱中检索实体和关系信息。

核心功能：
    - 实体检索：检索图谱中的实体
    - 关系检索：检索实体之间的关系
    - 路径检索：检索实体之间的路径

==============================================================================
"""

import logging
from typing import List, Dict, Any, Optional

from src.rag.agentic.state import Document

logger = logging.getLogger(__name__)


class GraphRetriever:
    """
    ==============================================================================
    图谱检索器
    ==============================================================================
    
    功能说明：
        基于知识图谱的检索器，用于从知识图谱中检索实体和关系信息。
    
    核心方法：
        - search(): 图谱检索
        - search_entity(): 实体检索
        - search_relationship(): 关系检索
    
    ==============================================================================
    """

    def __init__(self, uri: str = "bolt://localhost:7687", auth: tuple = None):
        """
        ==============================================================================
        初始化图谱检索器
        ==============================================================================
        
        参数说明：
            uri: Neo4j 数据库 URI
            auth: 认证信息 (username, password)
        
        ==============================================================================
        """
        self.uri = uri
        self.auth = auth
        self.driver = None
        
        # 尝试连接数据库
        try:
            import neo4j
            self.driver = neo4j.GraphDatabase.driver(uri, auth=auth)
            logger.info("GraphRetriever 连接成功")
        except Exception as e:
            logger.warning(f"GraphRetriever 连接失败: {e}")
            logger.warning("图谱检索器将以模拟模式运行")

    def search(
        self,
        query: str,
        top_k: int = 5,
        threshold: float = 0.5,
        filter: Optional[Dict[str, Any]] = None
    ) -> List[Document]:
        """
        ==============================================================================
        图谱检索
        ==============================================================================
        
        功能说明：
            从知识图谱中检索相关实体和关系。
        
        参数说明：
            query: 用户查询文本
            top_k: 返回的文档数量
            threshold: 相似度阈值
            filter: 元数据过滤器
        
        返回值：
            List[Document]: 检索到的文档列表
        
        ==============================================================================
        """
        logger.info(f"开始图谱检索: {query}")
        
        if not self.driver:
            logger.warning("图谱数据库未连接")
            return []
        
        try:
            # 提取查询中的实体
            entities = self._extract_entities(query)
            
            if not entities:
                return []
            
            # 检索实体和关系
            docs = []
            for entity in entities:
                entity_docs = self._search_entity(entity, top_k)
                docs.extend(entity_docs)
            
            # 过滤和排序
            docs = [d for d in docs if d.score >= threshold]
            docs.sort(key=lambda d: d.score, reverse=True)
            
            logger.info(f"图谱检索完成，返回 {len(docs)} 个文档")
            return docs[:top_k]
            
        except Exception as e:
            logger.error(f"图谱检索失败: {e}")
            return []

    def _extract_entities(self, query: str) -> List[str]:
        """
        ==============================================================================
        提取实体
        ==============================================================================
        
        功能说明：
            从查询中提取图谱中的实体。
        
        参数说明：
            query: 用户查询文本
        
        返回值：
            List[str]: 实体列表
        
        ==============================================================================
        """
        entities = []
        
        # 天干
        tiangan_pattern = r"[甲乙丙丁戊己庚辛壬癸]"
        for match in re.finditer(tiangan_pattern, query):
            entities.append(match.group())
        
        # 地支
        dizhi_pattern = r"[子丑寅卯辰巳午未申酉戌亥]"
        for match in re.finditer(dizhi_pattern, query):
            entities.append(match.group())
        
        # 五行
        wuxing_pattern = r"[金木水火土]"
        for match in re.finditer(wuxing_pattern, query):
            entities.append(match.group())
        
        # 十神
        shishen_pattern = r"[正官|七杀|偏官|正印|偏印|正财|偏财|食神|伤官|比肩|劫财]"
        for match in re.finditer(shishen_pattern, query):
            entities.append(match.group())
        
        return entities

    def _search_entity(self, entity: str, top_k: int) -> List[Document]:
        """
        ==============================================================================
        实体检索
        ==============================================================================
        
        功能说明：
            检索图谱中的实体及其相关信息。
        
        参数说明：
            entity: 实体名称
            top_k: 返回的文档数量
        
        返回值：
            List[Document]: 检索到的文档列表
        
        ==============================================================================
        """
        docs = []
        
        if not self.driver:
            # 模拟模式
            docs.append(Document(
                content=f"实体: {entity}",
                metadata={"type": "entity", "source": "graph"},
                score=0.8,
                source_type="graph"
            ))
            return docs
        
        try:
            with self.driver.session() as session:
                # 查询实体
                result = session.run(
                    """
                    MATCH (n {name: $name})
                    RETURN n LIMIT $limit
                    """,
                    name=entity,
                    limit=top_k
                )
                
                for record in result:
                    node = record["n"]
                    props = dict(node)
                    
                    docs.append(Document(
                        content=f"实体: {entity}, 属性: {props}",
                        metadata={
                            "type": "entity",
                            "source": "graph",
                            "entities": [entity]
                        },
                        score=0.9,
                        source_type="graph"
                    ))
                
                # 查询关系
                result = session.run(
                    """
                    MATCH (n {name: $name})-[r]->(m)
                    RETURN r, m LIMIT $limit
                    """,
                    name=entity,
                    limit=top_k
                )
                
                for record in result:
                    rel = record["r"]
                    end_node = record["m"]
                    
                    docs.append(Document(
                        content=f"关系: {type(rel).__name__}, 目标: {end_node['name']}",
                        metadata={
                            "type": "relationship",
                            "source": "graph",
                            "entities": [entity, end_node['name']]
                        },
                        score=0.85,
                        source_type="graph"
                    ))
        
        except Exception as e:
            logger.error(f"实体检索失败: {e}")
        
        return docs

    def search_relationship(
        self,
        entity1: str,
        entity2: str,
        relationship_type: str = None
    ) -> List[Document]:
        """
        ==============================================================================
        关系检索
        ==============================================================================
        
        功能说明：
            检索两个实体之间的关系。
        
        参数说明：
            entity1: 第一个实体
            entity2: 第二个实体
            relationship_type: 关系类型（可选）
        
        返回值：
            List[Document]: 检索到的文档列表
        
        ==============================================================================
        """
        docs = []
        
        if not self.driver:
            docs.append(Document(
                content=f"关系: {entity1} -> {entity2}",
                metadata={"type": "relationship", "source": "graph"},
                score=0.8,
                source_type="graph"
            ))
            return docs
        
        try:
            with self.driver.session() as session:
                if relationship_type:
                    result = session.run(
                        """
                        MATCH (n {name: $name1})-[r:`$type`]->(m {name: $name2})
                        RETURN r LIMIT 1
                        """,
                        name1=entity1,
                        name2=entity2,
                        type=relationship_type
                    )
                else:
                    result = session.run(
                        """
                        MATCH (n {name: $name1})-[r]->(m {name: $name2})
                        RETURN r LIMIT 1
                        """,
                        name1=entity1,
                        name2=entity2
                    )
                
                for record in result:
                    rel = record["r"]
                    docs.append(Document(
                        content=f"关系: {type(rel).__name__}",
                        metadata={
                            "type": "relationship",
                            "source": "graph",
                            "entities": [entity1, entity2]
                        },
                        score=0.9,
                        source_type="graph"
                    ))
        
        except Exception as e:
            logger.error(f"关系检索失败: {e}")
        
        return docs

    def search_path(
        self,
        entity1: str,
        entity2: str,
        max_depth: int = 3
    ) -> List[Document]:
        """
        ==============================================================================
        路径检索
        ==============================================================================
        
        功能说明：
            检索两个实体之间的所有路径。
        
        参数说明：
            entity1: 第一个实体
            entity2: 第二个实体
            max_depth: 最大深度
        
        返回值：
            List[Document]: 检索到的文档列表
        
        ==============================================================================
        """
        docs = []
        
        if not self.driver:
            docs.append(Document(
                content=f"路径: {entity1} -> {entity2}",
                metadata={"type": "path", "source": "graph"},
                score=0.8,
                source_type="graph"
            ))
            return docs
        
        try:
            with self.driver.session() as session:
                result = session.run(
                    """
                    MATCH p = shortestPath((n {name: $name1})-[*..$depth]-(m {name: $name2}))
                    RETURN p
                    """,
                    name1=entity1,
                    name2=entity2,
                    depth=max_depth
                )
                
                for record in result:
                    path = record["p"]
                    nodes = [node["name"] for node in path.nodes]
                    rels = [type(rel).__name__ for rel in path.relationships]
                    
                    docs.append(Document(
                        content=f"路径: {' -> '.join(nodes)}",
                        metadata={
                            "type": "path",
                            "source": "graph",
                            "entities": nodes,
                            "relationships": rels
                        },
                        score=0.85,
                        source_type="graph"
                    ))
        
        except Exception as e:
            logger.error(f"路径检索失败: {e}")
        
        return docs

    def close(self):
        """关闭数据库连接"""
        if self.driver:
            self.driver.close()
            logger.info("图谱检索器连接已关闭")
