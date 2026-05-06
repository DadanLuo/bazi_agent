"""Tokenizer 抽象层与默认启发式实现。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache
import json
import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class BaseTokenizer(ABC):
    """
    Tokenizer 抽象层。

    第一阶段目标不是立即接入模型原生 tokenizer，而是先把 token 计数能力抽象成可替换接口，
    避免预算分配器和 LLM 逻辑直接绑定某一种实现。
    """

    @abstractmethod
    def count_text(self, text: str) -> int:
        """统计纯文本 token 数。"""
        raise NotImplementedError

    @abstractmethod
    def count_messages(self, messages: List[Dict]) -> int:
        """统计消息数组 token 数。"""
        raise NotImplementedError

    @abstractmethod
    def trim_text(self, text: str, max_tokens: int) -> str:
        """按 token 预算裁剪纯文本。"""
        raise NotImplementedError


class HeuristicTokenizer(BaseTokenizer):
    """
    默认启发式 tokenizer。

    规则：
    - 中文约 1.5 字符 / token
    - ASCII 约 4 字符 / token

    它不等于模型原生 tokenizer，但胜在：
    - 无额外依赖
    - 运行稳定
    - 足以支撑第一阶段预算控制
    """

    def count_text(self, text: str) -> int:
        if not text:
            return 0
        chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        ascii_chars = len(text) - chinese_chars
        return int(chinese_chars / 1.5 + ascii_chars / 4)

    def count_messages(self, messages: List[Dict]) -> int:
        total = 0
        for message in messages or []:
            role = str(message.get("role", ""))
            name = str(message.get("name", ""))
            content = str(message.get("content", ""))
            tool_calls = json.dumps(message.get("tool_calls", []), ensure_ascii=False)
            total += self.count_text(f"{role}\n{name}\n{content}\n{tool_calls}")
        return total

    def trim_text(self, text: str, max_tokens: int) -> str:
        if self.count_text(text) <= max_tokens:
            return text

        low, high = 0, len(text)
        best = ""
        while low <= high:
            mid = (low + high) // 2
            candidate = text[:mid]
            tokens = self.count_text(candidate)
            if tokens <= max_tokens:
                best = candidate
                low = mid + 1
            else:
                high = mid - 1
        return best.strip()


class DashScopeQwenTokenizer(BaseTokenizer):
    """
    Qwen 家族 tokenizer 适配器。

    使用 dashscope 自带的本地 tokenizer 资源，不走远程 API。
    这是第二阶段的核心：让 Qwen 家族优先走真实 tokenizer，而不是启发式估算。
    """

    def __init__(self, model_name: str):
        from dashscope import get_tokenizer

        self.model_name = model_name
        self._tokenizer = get_tokenizer(model_name)

    def count_text(self, text: str) -> int:
        if not text:
            return 0
        return len(self._tokenizer.encode(text))

    def count_messages(self, messages: List[Dict]) -> int:
        total = 0
        for message in messages or []:
            role = str(message.get("role", ""))
            name = str(message.get("name", ""))
            content = str(message.get("content", ""))
            tool_calls = json.dumps(message.get("tool_calls", []), ensure_ascii=False)
            payload = f"<|{role}|>\n{name}\n{content}\n{tool_calls}\n"
            total += self.count_text(payload)
        return total

    def trim_text(self, text: str, max_tokens: int) -> str:
        if self.count_text(text) <= max_tokens:
            return text
        token_ids = self._tokenizer.encode(text)
        trimmed_ids = token_ids[:max_tokens]
        return self._tokenizer.decode(trimmed_ids).strip()


_DEFAULT_TOKENIZER = HeuristicTokenizer()
_TOKENIZER_MODEL_ALIASES = {
    "qwen3.5-plus": "qwen-plus",
    "qwen3.5-turbo": "qwen-turbo",
    "qwen3.5-max": "qwen-max",
    "qwen-long": "qwen-plus",
}


def _resolve_tokenizer_model_name(model_name: str) -> str:
    normalized = (model_name or "").strip().lower()
    if normalized in _TOKENIZER_MODEL_ALIASES:
        return _TOKENIZER_MODEL_ALIASES[normalized]

    for alias, target in _TOKENIZER_MODEL_ALIASES.items():
        if normalized.startswith(alias):
            return target
    return model_name


@lru_cache(maxsize=16)
def _build_tokenizer(model_name: str) -> BaseTokenizer:
    normalized = (model_name or "").strip().lower()

    if normalized.startswith("qwen"):
        try:
            tokenizer_model_name = _resolve_tokenizer_model_name(model_name)
            tokenizer = DashScopeQwenTokenizer(tokenizer_model_name)
            logger.info(
                "Tokenizer 适配成功: %s -> DashScopeQwenTokenizer(%s)",
                model_name,
                tokenizer_model_name,
            )
            return tokenizer
        except Exception as e:
            logger.warning("Qwen tokenizer 初始化失败，回退启发式实现: %s", e)

    logger.info("Tokenizer 使用启发式实现: %s", model_name or "default")
    return _DEFAULT_TOKENIZER


def get_tokenizer_for_model(model_name: Optional[str] = None) -> BaseTokenizer:
    """
    根据模型获取 tokenizer。

    第二阶段：
    - Qwen 家族优先走 DashScope 本地 tokenizer
    - 失败时优雅回退到启发式 tokenizer
    """

    if not model_name:
        return _DEFAULT_TOKENIZER
    return _build_tokenizer(model_name)


def estimate_tokens(text: str) -> int:
    """
    向后兼容入口。

    现有代码仍可继续使用 estimate_tokens()，内部已经走默认 tokenizer。
    """
    return _DEFAULT_TOKENIZER.count_text(text)
