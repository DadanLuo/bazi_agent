# src/llm/base.py
"""LLM 抽象接口 — 支持同步和异步调用，可配置模型参数"""
import asyncio
from abc import ABC, abstractmethod
from typing import List, Dict, Optional, Any
from pydantic import BaseModel


class LLMConfig(BaseModel):
    """LLM 配置"""
    model_name: str = "qwen-plus-latest"
    max_tokens: int = 16384
    temperature: float = 0.7
    timeout: int = 120
    max_retries: int = 1


class ToolCallResult(BaseModel):
    """Tool calling 返回结构"""
    content: Optional[str] = None          # 文本回复（无 tool call 时）
    tool_calls: List[Dict[str, Any]] = []  # tool call 列表
    finish_reason: str = "stop"            # stop / tool_calls

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0


class BaseLLM(ABC):
    """
    LLM 抽象基类

    所有 LLM 实现必须提供 call() 同步方法。
    acall() 默认通过 asyncio.to_thread 包装 call()，子类可覆盖为原生异步。
    """

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()

    @abstractmethod
    def call(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict]] = None,
    ) -> str:
        """同步调用"""
        ...

    async def acall(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict]] = None,
    ) -> str:
        """异步调用 — 默认用 to_thread 包装同步 call，子类可覆盖"""
        return await asyncio.to_thread(self.call, prompt, system_prompt, history)

    def call_with_tools(
        self,
        messages: List[Dict],
        tools: List[Dict],
        system_prompt: Optional[str] = None,
    ) -> ToolCallResult:
        """带 tool calling 的调用 — 子类覆盖实现"""
        raise NotImplementedError("call_with_tools not implemented")

    async def acall_with_tools(
        self,
        messages: List[Dict],
        tools: List[Dict],
        system_prompt: Optional[str] = None,
    ) -> ToolCallResult:
        """异步 tool calling"""
        return await asyncio.to_thread(self.call_with_tools, messages, tools, system_prompt)

    @abstractmethod
    def generate_bazi_report(self, bazi_data: Dict, knowledge_context: str) -> str:
        """生成八字报告"""
        ...

    async def agenerate_bazi_report(self, bazi_data: Dict, knowledge_context: str) -> str:
        """异步生成八字报告"""
        return await asyncio.to_thread(self.generate_bazi_report, bazi_data, knowledge_context)
