# src/graph/tarot_graph.py
"""塔罗牌 ReAct Agent — LLM 自主决策 Tool 调用"""
import json
import logging
from typing import Literal
from langgraph.graph import StateGraph, END
from src.graph.tarot_state import TarotAgentState

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 15  # 防止无限循环


def agent_node(state: TarotAgentState) -> dict:
    """Agent 节点 — LLM 决策下一步动作"""
    from src.dependencies import llm
    from src.agents.tarot_tools import TAROT_TOOLS
    from src.prompts.registry import TAROT_CONSTRAINTS

    messages = state.get("messages", [])
    iteration = state.get("iteration", 0)

    if iteration >= MAX_ITERATIONS:
        logger.warning("达到最大迭代次数，强制结束")
        return {
            "llm_response": messages[-1].get("content", "") if messages else "占卜完成。",
            "status": "completed",
            "iteration": iteration,
        }

    system_prompt = (
        f"{TAROT_CONSTRAINTS}\n\n"
        "你是一位专业的塔罗牌占卜师 Agent。你可以使用以下工具完成占卜：\n"
        "1. select_spread — 选择牌阵（根据问题复杂度自主判断）\n"
        "2. draw_cards — 抽牌\n"
        "3. interpret_single_card — 逐牌解读（可选，你也可以自己解读）\n"
        "4. retrieve_knowledge — 检索知识库补充解读\n"
        "5. synthesize_reading — 生成综合报告\n\n"
        "工作流程由你自主决定。一般建议：先选牌阵→抽牌→解读→综合。\n"
        "但你可以根据用户问题灵活调整，比如简单问题可以跳过逐牌解读直接综合。\n"
        "完成占卜后，直接用文字回复用户，不要再调用工具。"
    )

    result = llm.call_with_tools(
        messages=messages,
        tools=TAROT_TOOLS,
        system_prompt=system_prompt,
    )

    if result.has_tool_calls:
        # LLM 决定调用工具
        assistant_msg = {"role": "assistant", "content": result.content or ""}
        assistant_msg["tool_calls"] = result.tool_calls
        new_messages = messages + [assistant_msg]

        return {
            "messages": new_messages,
            "pending_tool_calls": result.tool_calls,
            "status": "tool_calling",
            "iteration": iteration + 1,
        }
    else:
        # LLM 直接回复，占卜结束
        content = result.content or ""
        new_messages = messages + [{"role": "assistant", "content": content}]

        return {
            "messages": new_messages,
            "llm_response": content,
            "status": "completed",
            "iteration": iteration + 1,
        }


def tool_node(state: TarotAgentState) -> dict:
    """Tool 执行节点 — 执行 LLM 请求的工具调用"""
    from src.agents.tarot_tools import TarotToolExecutor

    pending = state.get("pending_tool_calls", [])
    messages = state.get("messages", [])

    # 获取或创建 executor（通过 state 传递序列化状态）
    executor_state = state.get("executor_state", {})
    executor = TarotToolExecutor(conversation_id=state.get("conversation_id", ""))

    # 恢复 executor 状态
    if executor_state:
        executor.spread_info = executor_state.get("spread_info")
        executor.drawn_cards = executor_state.get("drawn_cards", [])
        executor.card_interpretations = executor_state.get("card_interpretations", [])
        executor.knowledge_context = executor_state.get("knowledge_context", "")

    new_messages = list(messages)

    for tc in pending:
        func_name = tc["function"]["name"]
        try:
            args = tc["function"]["arguments"]
            if isinstance(args, str):
                args = json.loads(args)
        except (json.JSONDecodeError, KeyError):
            args = {}

        logger.info(f"执行工具: {func_name}({args})")
        result_text = executor.execute(func_name, args)

        # 添加 tool result 消息
        new_messages.append({
            "role": "tool",
            "content": result_text,
            "name": func_name,
        })

    # 保存 executor 状态到 graph state
    updated_executor_state = executor.get_result()

    # 同步关键数据到顶层 state
    update = {
        "messages": new_messages,
        "pending_tool_calls": [],
        "executor_state": updated_executor_state,
        "status": "tool_executed",
    }

    if executor.drawn_cards:
        update["drawn_cards"] = executor.drawn_cards
    if executor.spread_info:
        update["spread_info"] = executor.spread_info

    return update


def safety_node(state: TarotAgentState) -> dict:
    """安全检查节点"""
    error = state.get("error")
    if error:
        return {
            "safe_output": {"error": error},
            "llm_response": state.get("llm_response", f"占卜过程中出现问题：{error}"),
            "status": "completed_with_error",
        }

    executor_state = state.get("executor_state", {})
    tarot_result = {
        "spread": state.get("spread_info"),
        "drawn_cards": state.get("drawn_cards", []),
        "card_interpretations": executor_state.get("card_interpretations", []),
        "synthesis": state.get("llm_response", ""),
    }

    return {
        "tarot_result": tarot_result,
        "safe_output": tarot_result,
        "status": "completed",
    }


def should_continue(state: TarotAgentState) -> Literal["tool_node", "safety_node"]:
    """路由：LLM 要调用工具 → tool_node，否则 → safety_node"""
    if state.get("status") == "tool_calling" and state.get("pending_tool_calls"):
        return "tool_node"
    return "safety_node"


def after_tool(state: TarotAgentState) -> Literal["agent_node"]:
    """工具执行完毕，回到 Agent 节点继续决策"""
    return "agent_node"


def create_tarot_graph() -> StateGraph:
    """创建塔罗牌 ReAct Agent Graph"""
    logger.info("正在构建塔罗牌 ReAct Agent Graph...")

    workflow = StateGraph(TarotAgentState)

    workflow.add_node("agent_node", agent_node)
    workflow.add_node("tool_node", tool_node)
    workflow.add_node("safety_node", safety_node)

    workflow.set_entry_point("agent_node")

    # Agent → Tool（需要调用工具）或 Safety（完成）
    workflow.add_conditional_edges("agent_node", should_continue, {
        "tool_node": "tool_node",
        "safety_node": "safety_node",
    })

    # Tool → Agent（回到 LLM 继续决策）
    workflow.add_conditional_edges("tool_node", after_tool, {
        "agent_node": "agent_node",
    })

    # Safety → END
    workflow.add_edge("safety_node", END)

    logger.info("塔罗牌 ReAct Agent Graph 构建完成")
    return workflow


tarot_graph = create_tarot_graph()
tarot_app = tarot_graph.compile()
