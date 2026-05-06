# src/agents/base.py
"""
Agent 基类 — 所有领域 Agent 的抽象接口

本模块定义了 Agent 的抽象基类和槽位模式，是多领域 Agent 扩展的核心。

设计模式：
- 抽象基类（ABC）：定义 Agent 接口规范
- 槽位模式（Slot Schema）：定义 Agent 需要的输入参数

使用方式：
    from src.agents.base import BaseAgent, SlotSchema
    
    class MyAgent(BaseAgent):
        @property
        def agent_id(self) -> str:
            return "my_agent"
        
        async def handle_analysis(self, session, slots, mode):
            # 实现分析逻辑
            pass
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

from src.core.contracts import UnifiedSession


class SlotSchema:
    """
    槽位定义 — 每个 Agent 声明自己需要的输入槽位
    
    槽位模式用于定义 Agent 需要的输入参数，支持必填校验和正则匹配。
    
    Attributes:
        slots: 槽位定义字典，格式如下：
            {
                "birth_year": {
                    "required": True,           # 是否必填
                    "pattern": r"(\d{4})[年\-]", # 正则匹配模式
                    "keywords": ["年"]           # 关键词匹配
                },
                ...
            }
    
    使用示例：
        schema = SlotSchema({
            "birth_year": {"required": True, "pattern": r"(\d{4})[年\-]", "keywords": ["年"]},
            "gender": {"required": True, "pattern": r"(男|女)", "keywords": ["性别", "男", "女"]}
        })
        missing = schema.get_missing({"birth_year": "1990年"})  # 返回 ["gender"]
    """

    def __init__(self, slots: Dict[str, Dict[str, Any]]):
        """
        初始化槽位定义
        
        Args:
            slots: 槽位定义字典
        """
        self.slots = slots

    def get_missing(self, filled: Dict[str, Any]) -> List[str]:
        """
        返回尚未填充的必需槽位名
        
        Args:
            filled: 已填充的槽位字典
            
        Returns:
            List[str]: 尚未填充的必需槽位名称列表
        """
        return [
            name for name, schema in self.slots.items()
            if schema.get("required") and name not in filled
        ]

    def get_required_names(self) -> List[str]:
        """
        获取所有必需槽位名
        
        Returns:
            List[str]: 必需槽位名称列表
        """
        return [name for name, schema in self.slots.items() if schema.get("required")]

    def get_all_names(self) -> List[str]:
        """
        获取所有槽位名
        
        Returns:
            List[str]: 所有槽位名称列表
        """
        return list(self.slots.keys())


class BaseAgent(ABC):
    """
    Agent 基类
    
    所有领域 Agent（八字、健康、事业、感情、塔罗等）继承此类，
    实现领域特定的分析逻辑。
    
    必须实现的抽象属性和方法：
    - agent_id: Agent 唯一标识
    - display_name: Agent 显示名称
    - slot_schema: 需要的输入槽位
    - intent_keywords: 意图检测关键词
    - handle_analysis: 主分析流程
    - handle_followup: 追问处理
    
    可选覆盖的方法：
    - get_domain_constraints: 领域特定的 LLM 约束
    """

    @property
    @abstractmethod
    def agent_id(self) -> str:
        """
        Agent 唯一标识
        
        Returns:
            str: Agent ID，如 'bazi', 'health', 'career', 'relationship', 'tarot'
        """
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """
        Agent 显示名称
        
        Returns:
            str: 显示名称，如 '八字命理分析'
        """
        ...

    @property
    @abstractmethod
    def slot_schema(self) -> SlotSchema:
        """
        该 Agent 需要的输入槽位
        
        Returns:
            SlotSchema: 槽位定义对象
        """
        ...

    @property
    @abstractmethod
    def intent_keywords(self) -> Dict[str, List[str]]:
        """
        意图检测关键词映射
        
        Returns:
            Dict[str, List[str]]: 意图类型到关键词列表的映射
                例如：{"NEW_ANALYSIS": ["分析", "算一下"], "FOLLOW_UP": ["然后", "接着"]}
        """
        ...

    @abstractmethod
    async def handle_analysis(
        self,
        session: UnifiedSession,
        slots: Dict[str, Any],
        mode: str = "full",
    ) -> Dict[str, Any]:
        """
        执行主分析流程
        
        Args:
            session: 统一会话对象
            slots: 已填充的槽位字典
            mode: 分析模式，"full" 为完整分析，"simple" 为简化分析
            
        Returns:
            Dict[str, Any]: 分析结果
                {
                    "response": str,      # 给用户的回复文本
                    "output": dict|None,  # 详细分析结果
                    ...                 # 其他领域特定数据
                }
        """
        ...

    @abstractmethod
    async def handle_followup(
        self,
        session: UnifiedSession,
        query: str,
    ) -> str:
        """
        处理追问，返回回复文本
        
        Args:
            session: 统一会话对象
            query: 用户的追问文本
            
        Returns:
            str: 回复文本
        """
        ...

    def get_domain_constraints(self) -> str:
        """
        领域特定的 LLM 约束，注入到每个 prompt 中
        
        默认返回空字符串，子类可以覆盖此方法来添加领域特定的约束。
        
        Returns:
            str: 领域约束字符串
        """
        return ""
