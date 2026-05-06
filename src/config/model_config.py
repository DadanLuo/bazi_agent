"""
统一模型配置中心。

目标：
1. 将模型名称、上下文窗口、输出 token、第三方 API 接入信息统一收口到 config
2. 提供 LLM 运行时配置转换，避免在调用层硬编码
3. 为上下文策略选择、预算控制提供单一事实来源
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional

from config.settings import settings

if TYPE_CHECKING:
    from src.llm.base import LLMConfig


DEFAULT_MODEL_NAME = "qwen3.5-plus"
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
UNKNOWN_MODEL_FALLBACK = "qwen-plus"


MODEL_CONFIGS: Dict[str, Dict[str, Any]] = {
    "qwen3.5-plus": {
        "provider": "dashscope-compatible",
        "base_url": DEFAULT_BASE_URL,
        "context_window": 1_000_000,
        "default_context_window": 262_144,
        "max_output_tokens": 65_536,
        "default_max_tokens": 16_384,
        "supports_streaming": True,
        "supports_tools": True,
        "tokenizer_model": "qwen-plus",
    },
    "qwen-plus": {
        "provider": "dashscope-compatible",
        "base_url": DEFAULT_BASE_URL,
        "context_window": 128_000,
        "default_context_window": 128_000,
        "max_output_tokens": 16_384,
        "default_max_tokens": 8_192,
        "supports_streaming": True,
        "supports_tools": True,
        "tokenizer_model": "qwen-plus",
    },
    "qwen-plus-latest": {
        "provider": "dashscope-compatible",
        "base_url": DEFAULT_BASE_URL,
        "context_window": 128_000,
        "default_context_window": 128_000,
        "max_output_tokens": 16_384,
        "default_max_tokens": 8_192,
        "supports_streaming": True,
        "supports_tools": True,
        "tokenizer_model": "qwen-plus",
    },
    "qwen-turbo": {
        "provider": "dashscope-compatible",
        "base_url": DEFAULT_BASE_URL,
        "context_window": 128_000,
        "default_context_window": 65_536,
        "max_output_tokens": 8_192,
        "default_max_tokens": 4_096,
        "supports_streaming": True,
        "supports_tools": True,
        "tokenizer_model": "qwen-turbo",
    },
    "qwen-max": {
        "provider": "dashscope-compatible",
        "base_url": DEFAULT_BASE_URL,
        "context_window": 32_768,
        "default_context_window": 32_768,
        "max_output_tokens": 8_192,
        "default_max_tokens": 4_096,
        "supports_streaming": True,
        "supports_tools": True,
        "tokenizer_model": "qwen-max",
    },
    "qwen-long": {
        "provider": "dashscope-compatible",
        "base_url": DEFAULT_BASE_URL,
        "context_window": 1_000_000,
        "default_context_window": 262_144,
        "max_output_tokens": 16_384,
        "default_max_tokens": 8_192,
        "supports_streaming": True,
        "supports_tools": False,
        "tokenizer_model": "qwen-plus",
    },
    "deepseek-v3": {
        "provider": "openai-compatible",
        "base_url": DEFAULT_BASE_URL,
        "context_window": 128_000,
        "default_context_window": 64_000,
        "max_output_tokens": 16_384,
        "default_max_tokens": 8_192,
        "supports_streaming": True,
        "supports_tools": True,
        "tokenizer_model": "qwen-plus",
    },
}
def _normalize_model_name(model_name: Optional[str]) -> str:
    raw_name = (model_name or "").strip()
    if raw_name:
        return raw_name
    return settings.resolved_llm_model_name or DEFAULT_MODEL_NAME


def _resolve_capability(model_name: str) -> Dict[str, Any]:
    normalized = model_name.strip().lower()
    if normalized in MODEL_CONFIGS:
        return MODEL_CONFIGS[normalized]

    for name, capability in MODEL_CONFIGS.items():
        if normalized.startswith(name):
            return capability

    return MODEL_CONFIGS[UNKNOWN_MODEL_FALLBACK]


@dataclass
class ModelConfig:
    """统一模型配置对象。"""

    requested_model_name: Optional[str] = None
    model_name: str = field(init=False)
    provider: str = field(init=False)
    api_key: Optional[str] = field(init=False)
    base_url: str = field(init=False)
    context_window: int = field(init=False)
    provider_context_window: int = field(init=False)
    max_output_tokens: int = field(init=False)
    max_tokens: int = field(init=False)
    temperature: float = field(init=False)
    timeout: int = field(init=False)
    max_retries: int = field(init=False)
    supports_streaming: bool = field(init=False)
    supports_tools: bool = field(init=False)
    tokenizer_model: str = field(init=False)
    extra_body: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        resolved_model_name = _normalize_model_name(self.requested_model_name)
        capability = _resolve_capability(resolved_model_name)

        self.model_name = resolved_model_name
        self.provider = capability.get("provider", "dashscope-compatible")
        self.api_key = settings.resolved_qwen_api_key
        self.base_url = settings.resolved_llm_base_url or capability.get(
            "base_url",
            DEFAULT_BASE_URL,
        )

        self.provider_context_window = int(capability.get("context_window", 131_072))
        default_context_window = int(
            capability.get("default_context_window", self.provider_context_window)
        )
        env_context_window = settings.resolved_llm_context_window
        self.context_window = max(
            min(env_context_window or default_context_window, self.provider_context_window),
            2_048,
        )

        self.max_output_tokens = int(capability.get("max_output_tokens", 16_384))
        default_max_tokens = int(capability.get("default_max_tokens", self.max_output_tokens))
        env_max_tokens = settings.resolved_llm_max_tokens
        self.max_tokens = max(
            min(env_max_tokens or default_max_tokens, self.max_output_tokens),
            256,
        )
        self.context_window = max(
            min(self.context_window, self.provider_context_window),
            min(self.provider_context_window, self.max_tokens + 1024),
        )

        self.temperature = settings.resolved_llm_temperature or 0.7
        self.timeout = max(settings.resolved_llm_timeout or 120, 30)
        self.max_retries = max(settings.resolved_llm_max_retries or 1, 0)
        self.supports_streaming = bool(capability.get("supports_streaming", True))
        self.supports_tools = bool(capability.get("supports_tools", True))
        self.tokenizer_model = str(capability.get("tokenizer_model", self.model_name))

    @property
    def max_output(self) -> int:
        """向后兼容旧命名。"""
        return self.max_output_tokens

    def to_llm_config(self) -> "LLMConfig":
        from src.llm.base import LLMConfig

        return LLMConfig(
            model_name=self.model_name,
            max_tokens=self.max_tokens,
            context_window=self.context_window,
            temperature=self.temperature,
            timeout=self.timeout,
            max_retries=self.max_retries,
            api_key=self.api_key,
            base_url=self.base_url,
            provider=self.provider,
            tokenizer_model=self.tokenizer_model,
            extra_body=dict(self.extra_body),
        )

    def apply_override(self, override: Optional["LLMConfig"]) -> "LLMConfig":
        from src.llm.base import LLMConfig

        merged = self.to_llm_config()
        if not override:
            return merged

        merged_data = merged.model_dump()
        for field_name in override.model_fields_set:
            value = getattr(override, field_name)
            if value is not None:
                merged_data[field_name] = value
        return LLMConfig(**merged_data)

    def get_max_history_tokens(self, reserve_ratio: float = 0.6) -> int:
        reserve_ratio = min(max(reserve_ratio, 0.1), 0.95)
        return int(self.context_window * reserve_ratio)

    def get_max_history_messages(self, avg_tokens_per_message: int = 300) -> int:
        avg_tokens_per_message = max(avg_tokens_per_message, 50)
        return max(self.get_max_history_tokens() // avg_tokens_per_message, 1)

    def __repr__(self) -> str:
        return (
            f"ModelConfig(model_name={self.model_name}, "
            f"context_window={self.context_window}, "
            f"max_tokens={self.max_tokens})"
        )


def get_default_model_config() -> ModelConfig:
    return ModelConfig()


class ContextStrategySelector:
    """根据模型窗口和查询类型选择上下文策略。"""

    MODEL_STRATEGY_HINTS = {
        "qwen-turbo": "SLIDING_WINDOW",
        "qwen-long": "FULL_CONTEXT",
        "deepseek-v3": "HYBRID",
    }

    @staticmethod
    def detect_query_type(query: Optional[str]) -> str:
        query_lower = (query or "").lower()
        if not query_lower.strip():
            return "GENERAL_CHAT"

        bazi_keywords = ["八字", "命理", "分析", "喜用神", "格局", "流年", "大运"]
        follow_up_keywords = ["那", "这个", "继续", "再说", "详细", "流年", "大运", "格局"]
        summary_keywords = ["总结", "概括", "简述", "要点"]

        if any(keyword in query_lower for keyword in summary_keywords):
            return "SUMMARY_REQUEST"
        if any(keyword in query_lower for keyword in bazi_keywords) and not any(
            keyword in query_lower for keyword in follow_up_keywords
        ):
            return "NEW_ANALYSIS"
        if any(keyword in query_lower for keyword in follow_up_keywords):
            return "FOLLOW_UP"
        return "GENERAL_CHAT"

    @classmethod
    def select_strategy(
        cls,
        query_type: str = "GENERAL_CHAT",
        model_name: Optional[str] = None,
        message_count: int = 0,
    ) -> str:
        if message_count is None or message_count <= 0:
            return "HYBRID"

        normalized_model_name = (model_name or "").strip().lower()
        if normalized_model_name in cls.MODEL_STRATEGY_HINTS:
            hinted = cls.MODEL_STRATEGY_HINTS[normalized_model_name]
            if hinted == "FULL_CONTEXT" and message_count >= 80:
                return "HYBRID"
            return hinted

        config = ModelConfig(model_name)

        if message_count >= 80:
            return "HYBRID"
        if query_type == "SUMMARY_REQUEST":
            return "SLIDING_WINDOW"
        if "turbo" in config.model_name.lower():
            return "SLIDING_WINDOW"
        if query_type == "FOLLOW_UP":
            return "HYBRID"
        if query_type == "NEW_ANALYSIS":
            return "FULL_CONTEXT" if config.context_window >= 128_000 else "HYBRID"
        if config.context_window >= 200_000:
            return "FULL_CONTEXT"
        return "HYBRID"

    @staticmethod
    def get_strategy_description(strategy: str) -> str:
        descriptions = {
            "FULL_CONTEXT": "全量上下文模式 - 使用所有历史对话作为上下文",
            "SLIDING_WINDOW": "滑动窗口模式 - 仅使用最近对话作为上下文",
            "HYBRID": "混合模式 - 使用关键消息 + 最近消息作为上下文",
        }
        return descriptions.get(strategy, "未知策略")
