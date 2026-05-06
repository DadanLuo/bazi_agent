from config.settings import settings
from src.config.model_config import ContextStrategySelector, ModelConfig
from src.config.rag_config import load_rag_config
from src.llm.dashscope_llm import DashScopeLLM


def test_model_config_defaults_to_qwen35_plus(monkeypatch):
    for key in [
        "LLM_MODEL_NAME",
        "QWEN_MODEL",
        "LLM_CONTEXT_WINDOW",
        "MAX_TOKENS",
        "LLM_MAX_TOKENS",
        "QWEN_BASE_URL",
        "QWEN_API_KEY",
        "DASHSCOPE_API_KEY",
    ]:
        monkeypatch.delenv(key, raising=False)

    config = ModelConfig()

    assert config.model_name == "qwen3.5-plus"
    assert config.context_window == 262144
    assert config.provider_context_window == 1_000_000
    assert config.max_tokens == 16384
    assert config.max_output_tokens == 65536
    assert config.tokenizer_model == "qwen-plus"


def test_model_config_honors_env_overrides(monkeypatch):
    monkeypatch.setenv("QWEN_MODEL", "qwen3.5-plus")
    monkeypatch.setenv("LLM_CONTEXT_WINDOW", "131072")
    monkeypatch.setenv("MAX_TOKENS", "8192")
    monkeypatch.setenv("QWEN_BASE_URL", "https://example.test/v1")

    config = ModelConfig()

    assert config.model_name == "qwen3.5-plus"
    assert config.context_window == 131072
    assert config.max_tokens == 8192
    assert config.base_url == "https://example.test/v1"


def test_dashscope_llm_uses_centralized_model_config(monkeypatch):
    monkeypatch.setenv("QWEN_MODEL", "qwen3.5-plus")
    monkeypatch.setenv("LLM_CONTEXT_WINDOW", "131072")
    monkeypatch.setenv("MAX_TOKENS", "8192")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-key")

    llm = DashScopeLLM()

    assert llm.model_name == "qwen3.5-plus"
    assert llm.context_window == 131072
    assert llm.max_tokens == 8192
    assert llm.base_url.endswith("/compatible-mode/v1")


def test_context_strategy_selector_prefers_full_context_for_qwen35plus():
    strategy = ContextStrategySelector.select_strategy(
        query_type="NEW_ANALYSIS",
        model_name="qwen3.5-plus",
        message_count=5,
    )

    assert strategy == "FULL_CONTEXT"


def test_settings_resolve_api_key_alias(monkeypatch):
    monkeypatch.delenv("QWEN_API_KEY", raising=False)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "fallback-key")

    assert settings.resolved_qwen_api_key == "fallback-key"
    assert settings.resolved_embedding_api_key == "fallback-key"


def test_load_rag_config_uses_centralized_settings(monkeypatch):
    monkeypatch.setenv("RAG_EMBEDDING_MODEL", "text-embedding-v5")
    monkeypatch.setenv("RAG_INDEX_VERSION", "v3")

    config = load_rag_config()

    assert config.embedding_model == "text-embedding-v5"
    assert config.index_version == "v3"
