# src/agents/base.py
"""
Agent 基类 — 所有领域 Agent 的抽象接口
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional

from src.core.contracts import UnifiedSession


class SlotSchema:
    """
    槽位定义 — 每个 Agent 声明自己需要的输入槽位

    slots 格式: {
        "birth_year": {"required": True, "pattern": r"(\d{4})[年\-]", "keywords": ["年"]},
        ...
    }
    """

    def __init__(self, slots: Dict[str, Dict[str, Any]]):
        self.slots = slots

    def get_missing(self, filled: Dict[str, Any]) -> List[str]:
        """返回尚未填充的必需槽位名"""
        return [
            name for name, schema in self.slots.items()
            if schema.get("required") and name not in filled
        ]

    def get_required_names(self) -> List[str]:
        return [name for name, schema in self.slots.items() if schema.get("required")]

    def get_all_names(self) -> List[str]:
        return list(self.slots.keys())


class BaseAgent(ABC):
    """
    Agent 基类

    每个领域 Agent（八字、健康、事业、感情等）继承此类，实现：
    - agent_id / display_name: 标识
    - slot_schema: 需要的输入槽位
    - intent_keywords: 意图检测关键词
    - handle_analysis: 主分析流程
    - handle_followup: 追问处理
    - get_domain_constraints: 领域特定的 LLM 约束
    """

    @property
    @abstractmethod
    def agent_id(self) -> str:
        """唯一标识: 'bazi', 'health', 'career', 'relationship'"""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """显示名称"""
        ...

    @property
    @abstractmethod
    def slot_schema(self) -> SlotSchema:
        """该 Agent 需要的输入槽位"""
        ...

    @property
    @abstractmethod
    def intent_keywords(self) -> Dict[str, List[str]]:
        """意图检测关键词映射"""
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

        Returns:
            {"response": str, "output": dict|None}
        """
        ...

    @abstractmethod
    async def handle_followup(
        self,
        session: UnifiedSession,
        query: str,
    ) -> str:
        """处理追问，返回回复文本"""
        ...

    def get_domain_constraints(self) -> str:
        """领域特定的 LLM 约束，注入到每个 prompt 中。默认为空，子类覆盖。"""
        return ""
