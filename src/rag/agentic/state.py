"""
==============================================================================
Agentic RAG 状态定义
==============================================================================

功能说明：
    本模块定义了 Agentic RAG 系统的所有状态类型和数据模型，包括：
    - AgentState: Agent 状态枚举
    - Document: 文档数据模型
    - QueryAnalysis: 查询分析结果
    - RetrievalPlan: 检索计划
    - EvaluationResult: 评估结果
    - ReflectionResult: 反思结果
    - SearchRecord: 搜索历史记录
    - ConversationContext: 对话上下文
    - AgenticRAGState: LangGraph 状态定义

==============================================================================
"""

from typing import TypedDict, List, Dict, Any, Optional
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime


class AgentState(str, Enum):
    """Agent 状态枚举"""
    INITIALIZED = "initialized"           # 初始化完成
    ANALYZING = "analyzing"               # 分析中
    PLANNING = "planning"                 # 规划中
    RETRIEVING = "retrieving"             # 检索中
    EVALUATING = "evaluating"             # 评估中
    REFLECTING = "reflecting"             # 反思中
    SYNTHESIZING = "synthesizing"         # 整合中
    COMPLETED = "completed"               # 完成
    FAILED = "failed"                     # 失败


@dataclass
class Document:
    """
    ==============================================================================
    文档数据模型
    ==============================================================================
    
    功能说明：
        表示检索到的文档，包含文档内容、元数据和检索相关的信息。
    
    属性：
        content: 文档内容
        metadata: 元数据（来源、类型、分数等）
        score: 检索分数
        source_type: 来源类型（vector/bm25/graph）
    
    ==============================================================================
    """
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    source_type: str = "vector"
    
    @property
    def source(self) -> Optional[str]:
        """获取文档来源"""
        return self.metadata.get("source")
    
    @property
    def page(self) -> Optional[int]:
        """获取页码"""
        return self.metadata.get("page")


@dataclass
class QueryAnalysis:
    """
    ==============================================================================
    查询分析结果
    ==============================================================================
    
    功能说明：
        存储查询分析器的分析结果，包括意图、复杂度、关键实体等信息。
    
    属性：
        intent: 意图类型
        complexity: 复杂度
        need_retrieval: 是否需要检索
        suggested_sources: 建议的知识源
        key_entities: 关键实体
        reasoning_type: 推理类型
        confidence: 分析置信度
        entities: 提取的实体列表
        query_type: 查询类型
    
    ==============================================================================
    """
    intent: str                           # 意图类型
    complexity: str                       # 复杂度（简单/中等/复杂）
    need_retrieval: bool                  # 是否需要检索
    suggested_sources: List[str]          # 建议的知识源
    key_entities: List[str]               # 关键实体
    reasoning_type: str                   # 推理类型
    confidence: float                     # 分析置信度 (0-1)
    entities: List[Dict[str, Any]] = field(default_factory=list)  # 实体详情
    query_type: str = "normal"            # 查询类型


@dataclass
class RetrievalPlan:
    """
    ==============================================================================
    检索计划
    ==============================================================================
    
    功能说明：
        存储检索规划器制定的检索策略，包括使用的工具、执行顺序、参数等。
    
    属性：
        tools: 使用的检索工具列表
        order: 执行顺序
        params: 检索参数
        fusion_strategy: 融合策略
        max_iterations: 最大迭代次数
    
    ==============================================================================
    """
    tools: List[str]                      # 使用的检索工具
    order: List[str]                      # 执行顺序
    params: Dict[str, Any]                # 检索参数
    fusion_strategy: str                  # 融合策略
    max_iterations: int                   # 最大迭代次数


@dataclass
class EvaluationResult:
    """
    ==============================================================================
    评估结果
    ==============================================================================
    
    功能说明：
        存储结果评估器的评估结果，包括相关性、覆盖度、多样性等分数。
    
    属性：
        relevance_score: 相关性分数 (0-1)
        coverage_score: 覆盖度分数 (0-1)
        diversity_score: 多样性分数 (0-1)
        freshness_score: 新鲜度分数 (0-1)
        overall_score: 综合分数 (0-1)
        need_more: 是否需要更多信息
        gaps: 信息缺口
        suggestions: 优化建议
    
    ==============================================================================
    """
    relevance_score: float                # 相关性分数 (0-1)
    coverage_score: float                 # 覆盖度分数 (0-1)
    diversity_score: float                # 多样性分数 (0-1)
    freshness_score: float                # 新鲜度分数 (0-1)
    overall_score: float                  # 综合分数 (0-1)
    need_more: bool                       # 是否需要更多信息
    gaps: List[str] = field(default_factory=list)           # 信息缺口
    suggestions: List[str] = field(default_factory=list)    # 优化建议


@dataclass
class ReflectionResult:
    """
    ==============================================================================
    反思结果
    ==============================================================================
    
    功能说明：
        存储反思引擎生成的优化方案，包括失败原因、查询优化建议等。
    
    属性：
        failure_reason: 失败原因
        query_refinement: 查询优化建议
        strategy_adjustment: 策略调整
        next_action: 下一步动作
    
    ==============================================================================
    """
    failure_reason: str                   # 失败原因
    query_refinement: str                 # 查询优化建议
    strategy_adjustment: Dict[str, Any]   # 策略调整
    next_action: str                      # 下一步动作


@dataclass
class SearchRecord:
    """
    ==============================================================================
    搜索历史记录
    ==============================================================================
    
    功能说明：
        记录每次搜索的详细信息，用于反思和优化。
    
    属性：
        query: 搜索查询
        timestamp: 搜索时间
        tools: 使用的工具
        docs_count: 返回文档数量
        evaluation: 评估结果
    
    ==============================================================================
    """
    query: str                            # 搜索查询
    timestamp: datetime                   # 搜索时间
    tools: List[str]                      # 使用的工具
    docs_count: int                       # 返回文档数量
    evaluation: Optional[EvaluationResult] = None  # 评估结果


@dataclass
class ConversationContext:
    """
    ==============================================================================
    对话上下文
    ==============================================================================
    
    功能说明：
        存储多轮对话的上下文信息，用于查询补全和上下文感知检索。
    
    属性：
        conversation_id: 对话ID
        user_id: 用户ID
        turn_count: 对话轮数
        bazi_result: 八字分析结果
        wuxing_analysis: 五行分析结果
        geju: 格局
        yongshen: 喜用神
        retrieved_knowledge: 已检索的知识
        search_queries: 搜索查询历史
        last_topic: 上一个话题
    
    ==============================================================================
    """
    conversation_id: str                  # 对话ID
    user_id: str                          # 用户ID
    turn_count: int = 0                   # 对话轮数
    bazi_result: Optional[Dict[str, Any]] = None      # 八字分析结果
    wuxing_analysis: Optional[Dict[str, Any]] = None  # 五行分析结果
    geju: Optional[str] = None            # 格局
    yongshen: Optional[List[str]] = None  # 喜用神
    retrieved_knowledge: List[Document] = field(default_factory=list)  # 已检索的知识
    search_queries: List[str] = field(default_factory=list)            # 搜索查询历史
    last_topic: str = ""                  # 上一个话题


class AgenticRAGState(TypedDict, total=False):
    """
    ==============================================================================
    Agentic RAG 状态定义
    ==============================================================================
    
    功能说明：
        LangGraph 工作流的状态定义，包含所有节点之间传递的数据。
        total=False 表示所有字段都是可选的。
    
    输入字段：
        original_query: 原始查询
        current_query: 当前查询（可能被重写）
        conversation_context: 对话上下文
    
    分析结果：
        query_analysis: 查询分析结果
    
    检索控制：
        iteration: 当前迭代次数
        max_iterations: 最大迭代次数
        retrieval_plan: 检索计划
        current_action: 当前动作
    
    检索结果：
        retrieved_docs: 检索到的文档列表
        search_history: 搜索历史
    
    评估结果：
        evaluation: 评估结果
        reflection: 反思结果
    
    输出字段：
        final_context: 最终上下文
        reasoning_trace: 推理轨迹
    
    状态字段：
        state: 当前状态
        error: 错误信息
    
    ==============================================================================
    """
    # 输入
    original_query: str                   # 原始查询
    current_query: str                    # 当前查询（可能被重写）
    conversation_context: Optional[ConversationContext]  # 对话上下文
    graph_state: Optional[Dict[str, Any]]  # 上游八字 LangGraph 完整运行时状态
    
    # 分析结果
    query_analysis: Optional[Dict[str, Any]]  # 查询分析结果
    
    # 检索控制
    iteration: int                        # 当前迭代次数
    max_iterations: int                   # 最大迭代次数
    retrieval_plan: Optional[Dict[str, Any]]  # 检索计划
    current_action: str                   # 当前动作
    
    # 检索结果
    retrieved_docs: List[Dict[str, Any]]  # 检索到的文档列表
    search_history: List[Dict[str, Any]]  # 搜索历史
    
    # 评估结果
    evaluation: Optional[Dict[str, Any]]  # 评估结果
    reflection: Optional[Dict[str, Any]]  # 反思结果
    
    # 输出
    final_context: str                    # 最终上下文
    reasoning_trace: List[str]            # 推理轨迹
    
    # 状态
    state: AgentState                     # 当前状态
    error: Optional[str]                  # 错误信息
