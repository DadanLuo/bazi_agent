from src.core.context_budget import ContextBudgetAllocator, ContextModule
from src.llm.base import LLMConfig
from src.llm.dashscope_llm import DashScopeLLM


def test_allocator_preserves_multiple_domains_under_budget():
    text = (
        "【总论】命局整体偏强，需要综合看待。\n\n"
        "【健康】健康方面要注意睡眠、压力和身体恢复，健康领域内容。" + "健" * 300 + "\n\n"
        "【财运】财运方面更适合稳健积累，避免激进决策，财运领域内容。" + "财" * 300 + "\n\n"
        "【事业】事业上更适合循序渐进，面试和岗位选择都很关键，事业领域内容。" + "事" * 300 + "\n\n"
        "【爱情】爱情和亲密关系要重视沟通与边界，爱情领域内容。" + "爱" * 300
    )

    allocator = ContextBudgetAllocator(
        model_name="unit-test-model",
        context_window=1200,
        reserved_output_tokens=512,
        safety_margin_tokens=128,
    )
    result = allocator.allocate(
        modules=[
            ContextModule(
                name="structured_context",
                content=text,
                ratio=1.0,
                strategy="structured_context",
                preserve_domains=True,
            )
        ],
        prompt_overhead_text="上下文：\n{context}\n\n问题：请综合说明",
        strategy_name="HYBRID",
    )

    content = result.get("structured_context")
    assert "【健康相关】" in content
    assert "【财运相关】" in content
    assert "【事业相关】" in content
    assert "【爱情相关】" in content


def test_recent_history_prefers_latest_messages():
    history = "\n".join(
        [f"user: 第{i}条历史消息，包含一些上下文说明。" + ("旧" * 80) for i in range(1, 9)]
    )
    allocator = ContextBudgetAllocator(
        model_name="unit-test-model",
        context_window=820,
        reserved_output_tokens=700,
        safety_margin_tokens=128,
    )
    result = allocator.allocate(
        modules=[
            ContextModule(
                name="recent_history",
                content=history,
                ratio=1.0,
                strategy="recent_history",
                preserve_domains=False,
            )
        ],
        prompt_overhead_text="追问：请继续说明",
        strategy_name="SLIDING_WINDOW",
    )

    content = result.get("recent_history")
    assert "第8条历史消息" in content
    assert "第1条历史消息" not in content


def test_dashscope_message_trimming_keeps_latest_messages():
    llm = DashScopeLLM(
        config=LLMConfig(
            model_name="qwen3.5-plus",
            max_tokens=512,
            context_window=2048,
        )
    )
    messages = [
        {"role": "user", "content": f"第{i}轮消息 " + ("内容" * 120)}
        for i in range(1, 8)
    ]

    trimmed = llm._trim_messages_to_budget(messages, token_budget=240)

    assert len(trimmed) < len(messages)
    assert "第7轮消息" in trimmed[-1]["content"]
    assert all("第1轮消息" not in message["content"] for message in trimmed)


def test_finalize_prompt_rebalances_when_template_pushes_over_budget():
    allocator = ContextBudgetAllocator(
        model_name="unit-test-model",
        context_window=1024,
        reserved_output_tokens=512,
        safety_margin_tokens=128,
    )
    large_structured = "【事业】" + ("事业分析内容" * 60)
    large_retrieval = "【相关知识】" + ("知识片段" * 50)
    allocation = allocator.allocate(
        modules=[
            ContextModule(
                name="structured_context",
                content=large_structured,
                ratio=0.7,
                strategy="structured_context",
                preserve_domains=True,
                priority=10,
            ),
            ContextModule(
                name="retrieval_context",
                content=large_retrieval,
                ratio=0.3,
                strategy="rag_documents",
                preserve_domains=True,
                priority=30,
            ),
        ],
        prompt_overhead_text="上下文：\n{context}\n\n追问：请结合背景完整作答",
        strategy_name="HYBRID",
    )

    prompt_result = allocation.finalize_prompt(
        lambda module_texts: (
            "上下文：\n"
            + module_texts.get("structured_context", "")
            + "\n\n"
            + module_texts.get("retrieval_context", "")
            + "\n\n追问：请结合背景完整作答"
            + ("补充说明" * 40)
        )
    )

    assert prompt_result.prompt_tokens <= prompt_result.max_prompt_tokens
    assert prompt_result.adjusted is True
    assert len(prompt_result.trimmed_modules) >= 1
