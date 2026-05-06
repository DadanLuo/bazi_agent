from src.core.tokenizer import (
    BaseTokenizer,
    HeuristicTokenizer,
    estimate_tokens,
    get_tokenizer_for_model,
)


def test_get_tokenizer_for_model_returns_base_tokenizer():
    tokenizer = get_tokenizer_for_model("qwen3.5-plus")
    assert isinstance(tokenizer, BaseTokenizer)


def test_heuristic_tokenizer_matches_legacy_estimate_tokens():
    text = "八字分析 mixed context 123"
    tokenizer = HeuristicTokenizer()
    assert tokenizer.count_text(text) == estimate_tokens(text)


def test_heuristic_tokenizer_counts_messages_and_trims():
    tokenizer = HeuristicTokenizer()
    messages = [
        {"role": "user", "content": "第一条消息"},
        {"role": "assistant", "content": "第二条回复"},
    ]
    total = tokenizer.count_messages(messages)
    trimmed = tokenizer.trim_text("这是一个很长的上下文文本" * 20, max_tokens=20)

    assert total > 0
    assert tokenizer.count_text(trimmed) <= 20
