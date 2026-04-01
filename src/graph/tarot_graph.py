# src/graph/tarot_graph.py
"""
==============================================================================
塔罗牌 ReAct Agent — LLM 自主决策 Tool 调用
==============================================================================

功能说明：
    本模块定义了塔罗牌占卜的 LangGraph ReAct Agent 工作流。ReAct（Reasoning + Action）
    模式允许 LLM 通过推理自主决定调用哪些工具来完成占卜任务。

工作流节点：
    1. agent_node - Agent 节点，LLM 决策下一步动作
    2. tool_node - Tool 执行节点，执行 LLM 请求的工具调用
    3. safety_node - 安全检查节点，进行输入和输出内容审核

执行流程：
    agent_node → tool_node (如果需要调用工具) → agent_node (继续决策)
    agent_node → safety_node (完成占卜) → END

工具调用：
    1. select_spread - 选择牌阵（根据问题复杂度自主判断）
    2. draw_cards - 抽牌
    3. interpret_single_card - 逐牌解读（可选）
    4. retrieve_knowledge - 检索知识库补充解读
    5. synthesize_reading - 生成综合报告

==============================================================================
"""

import json
import logging
from typing import Literal
from langgraph.graph import StateGraph, END
from src.graph.tarot_state import TarotAgentState
from src.safety.safety import SafetyChecker, SafetyLevel

logger = logging.getLogger(__name__)

# 全局安全检查器 - 在模块加载时初始化
_safety_checker = None
try:
    _safety_checker = SafetyChecker()
except Exception as e:
    logger.warning(f"⚠️ 安全检查器初始化失败: {e}")

# 最大迭代次数 - 防止无限循环
MAX_ITERATIONS = 15


def agent_node(state: TarotAgentState) -> dict:
    """
    ==============================================================================
    Agent 节点 — LLM 决策下一步动作
    ==============================================================================
    
    功能说明：
        Agent 节点是 ReAct Agent 的核心，负责调用 LLM 进行推理并决定下一步动作。
        LLM 会根据当前对话历史和任务目标，决定是否需要调用工具。
    
    参数说明：
        state (TarotAgentState): 当前工作流状态，包含：
            - messages: 对话历史
            - iteration: 当前迭代次数
    
    返回值：
        dict: 更新后的状态，包含：
            - messages: 更新后的对话历史
            - pending_tool_calls: 待执行的工具调用列表
            - llm_response: LLM 的直接回复（如果不需要调用工具）
            - status: 当前状态（"tool_calling" 或 "completed"）
            - iteration: 更新后的迭代次数
    
    执行流程：
        1. 检查是否达到最大迭代次数
        2. 构建系统提示词，包含可用工具列表
        3. 调用 LLM 的 call_with_tools 方法
        4. 根据 LLM 的响应决定下一步动作：
           - 如果有工具调用 → 返回 "tool_calling" 状态
           - 如果直接回复 → 返回 "completed" 状态
    
    ==============================================================================
    """
    from src.dependencies import llm
    from src.agents.tarot_tools import TAROT_TOOLS
    from src.prompts.registry import TAROT_CONSTRAINTS

    messages = state.get("messages", [])
    iteration = state.get("iteration", 0)

    # 检查是否达到最大迭代次数，防止无限循环
    if iteration >= MAX_ITERATIONS:
        logger.warning("达到最大迭代次数，强制结束")
        return {
            "llm_response": messages[-1].get("content", "") if messages else "占卜完成。",
            "status": "completed",
            "iteration": iteration,
        }

    # 构建系统提示词，告诉 LLM 可用的工具和工作流程
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

    # 调用 LLM 的 call_with_tools 方法
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
    """
    ==============================================================================
    Tool 执行节点 — 执行 LLM 请求的工具调用
    ==============================================================================
    
    功能说明：
        Tool 节点负责执行 LLM 决定调用的工具。每个工具执行后，将结果添加到
        对话历史中，然后回到 Agent 节点继续决策。
    
    参数说明：
        state (TarotAgentState): 当前工作流状态，包含：
            - pending_tool_calls: 待执行的工具调用列表
            - messages: 对话历史
            - executor_state: 工具执行器状态
    
    返回值：
        dict: 更新后的状态，包含：
            - messages: 添加了工具调用结果的对话历史
            - pending_tool_calls: 清空的待执行工具列表
            - executor_state: 更新后的工具执行器状态
            - drawn_cards: 抽牌结果（如果执行了抽牌工具）
            - spread_info: 牌阵信息（如果执行了选择牌阵工具）
            - status: "tool_executed"
    
    工具执行流程：
        1. 恢复工具执行器状态
        2. 遍历待执行的工具调用
        3. 解析工具参数
        4. 执行工具
        5. 将工具结果添加到对话历史
        6. 保存工具执行器状态
    
    ==============================================================================
    """
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

    # 遍历待执行的工具调用
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

        # 添加 tool result 消息到对话历史
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

    # 如果执行了抽牌工具，同步抽牌结果
    if executor.drawn_cards:
        update["drawn_cards"] = executor.drawn_cards
    # 如果执行了选择牌阵工具，同步牌阵信息
    if executor.spread_info:
        update["spread_info"] = executor.spread_info

    return update


def safety_node(state: TarotAgentState) -> dict:
    """
    ==============================================================================
    安全检查节点 - 集成输入和输出内容审核
    ==============================================================================
    
    功能说明：
        安全节点在占卜完成前进行最终的内容审核，确保输入和输出内容的安全性。
        包括用户输入审核和 LLM 输出审核两部分。
    
    参数说明：
        state (TarotAgentState): 当前工作流状态，包含：
            - user_input: 用户原始输入
            - user_query: 用户查询文本
            - llm_response: LLM 生成的回复
    
    返回值：
        dict: 更新后的状态，包含：
            - safe_output: 安全输出结果
            - llm_response: 安全的回复文本
            - tarot_result: 塔罗占卜结果（如果通过审核）
            - status: "safety_blocked" 或 "completed"
    
    安全检查流程：
        1. 检查用户原始输入
        2. 检查 LLM 输出
        3. 如果通过审核，构建塔罗占卜结果
        4. 返回安全的结果
    
    ==============================================================================
    """
    logger.info("=" * 30)
    logger.info("【塔罗安全节点】执行安全检查...")
    
    # 检查用户原始输入
    user_input = state.get("user_input", {})
    user_query = state.get("user_query", "")
    
    if _safety_checker and (user_input or user_query):
        input_text = user_query or str(user_input)
        input_result = _safety_checker.check_input(input_text)
        
        if input_result.blocked:
            logger.warning(f"❌ 用户输入被阻断: {input_result.matched_keywords}")
            return {
                "safe_output": {
                    "message": input_result.message,
                    "data": None,
                    "blocked": True,
                    "blocked_category": input_result.category.value if input_result.category else None,
                },
                "llm_response": input_result.message,
                "status": "safety_blocked",
            }
        
        if input_result.level == SafetyLevel.WARNING:
            logger.warning(f"⚠️ 用户输入有风险: {input_result.matched_keywords}")
    
    # 检查 LLM 输出
    llm_response = state.get("llm_response", "")
    
    if _safety_checker and llm_response:
        output_result = _safety_checker.check_output(llm_response)
        
        if output_result.blocked:
            logger.warning(f"❌ LLM输出被阻断: {output_result.matched_keywords}")
            safe_response = _safety_checker.get_safe_response(
                output_result.category,
                SafetyLevel.BLOCK
            )
            return {
                "safe_output": {
                    "message": safe_response,
                    "data": None,
                    "blocked": True,
                    "blocked_category": output_result.category.value if output_result.category else None,
                },
                "llm_response": safe_response,
                "status": "safety_blocked",
            }
    
    # 通过安全检查，构建塔罗结果
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
        "synthesis": llm_response,
    }

    logger.info("✅ 塔罗安全检查通过")
    logger.info("=" * 30)
    
    return {
        "tarot_result": tarot_result,
        "safe_output": tarot_result,
        "status": "completed",
    }


def should_continue(state: TarotAgentState) -> Literal["tool_node", "safety_node"]:
    """
    ==============================================================================
    路由：LLM 要调用工具 → tool_node，否则 → safety_node
    ==============================================================================
    
    功能说明：
        在 Agent 节点执行后，根据 LLM 的响应决定下一步执行的节点。
        如果 LLM 决定调用工具，则进入 Tool 节点；否则进入安全检查节点。
    
    参数说明：
        state (TarotAgentState): 当前工作流状态
    
    返回值：
        Literal["tool_node", "safety_node"]: 下一步执行的节点名称
    
    路由逻辑：
        - status == "tool_calling" 且有 pending_tool_calls → "tool_node"
        - 其他情况 → "safety_node"
    
    ==============================================================================
    """
    if state.get("status") == "tool_calling" and state.get("pending_tool_calls"):
        return "tool_node"
    return "safety_node"


def after_tool(state: TarotAgentState) -> Literal["agent_node"]:
    """
    ==============================================================================
    工具执行完毕，回到 Agent 节点继续决策
    ==============================================================================
    
    功能说明：
        在 Tool 节点执行完毕后，回到 Agent 节点继续进行推理和决策。
        Agent 节点会根据工具执行结果更新对话历史，并决定下一步动作。
    
    参数说明：
        state (TarotAgentState): 当前工作流状态
    
    返回值：
        Literal["agent_node"]: 下一步执行的节点名称
    
    路由逻辑：
        - 始终返回 "agent_node"
    
    ==============================================================================
    """
    return "agent_node"


def create_tarot_graph() -> StateGraph:
    """
    ==============================================================================
    创建塔罗牌 ReAct Agent Graph
    ==============================================================================
    
    功能说明：
        构建塔罗牌占卜的 LangGraph ReAct Agent 工作流。
        工作流采用 ReAct 模式，允许 LLM 通过推理自主决定调用工具。
    
    返回值：
        StateGraph: 构建完成的状态图对象
    
    工作流结构：
        1. agent_node (入口节点) - LLM 决策
        2. tool_node - 执行工具调用
        3. safety_node - 安全检查
        4. END - 工作流结束
    
    路由逻辑：
        - agent_node → tool_node (需要调用工具)
        - agent_node → safety_node (完成占卜)
        - tool_node → agent_node (继续决策)
        - safety_node → END (结束)
    
    ==============================================================================
    """
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


# 实例化图 - 在模块加载时创建并编译图
tarot_graph = create_tarot_graph()
tarot_app = tarot_graph.compile()
