# src/agents/tarot_agent.py
"""
==============================================================================
塔罗牌占卜 Agent — LangGraph 驱动的自主决策组件
==============================================================================

功能说明：
    本模块实现了塔罗牌占卜的 Agent，负责处理用户的塔罗占卜请求和后续追问。
    采用 ReAct Agent 模式，通过 LangGraph 工作流驱动 LLM 自主决策调用工具
    （选择牌阵、抽牌、解读、综合报告等）完成占卜流程。

主要职责：
    1. 槽位提取：从用户输入中提取问题类型、牌阵类型、具体问题等信息
    2. 意图识别：识别用户意图（新占卜、追问、话题切换、澄清等）
    3. 占卜流程：通过 LangGraph 执行完整的塔罗占卜流程（ReAct 模式）
    4. 追问处理：结合占卜结果进行塔罗相关问题的追问回答

使用场景：
    - 用户请求塔罗牌占卜
    - 用户对占卜结果进行追问
    - 用户切换到其他占卜话题

==============================================================================
"""

import logging
from typing import Dict, Any, List

from src.agents.base import BaseAgent, SlotSchema
from src.core.contracts import UnifiedSession
from src.prompts.registry import PromptRegistry, TAROT_CONSTRAINTS

logger = logging.getLogger(__name__)


class TarotAgent(BaseAgent):
    """
    ==============================================================================
    塔罗牌占卜 Agent
    ==============================================================================
    
    功能说明：
        塔罗牌占卜 Agent，负责处理用户的塔罗占卜请求和后续追问。
        继承自 BaseAgent，实现了塔罗占卜领域的特定逻辑。
    
    核心特性：
        1. 槽位提取：定义了塔罗占卜所需的槽位模式（问题类型、牌阵、具体问题）
        2. 意图识别：定义了五种意图类型的关键词（新占卜、追问、话题切换、澄清、通用查询）
        3. ReAct 模式：通过 LangGraph 驱动 LLM 自主决策调用工具完成占卜
        4. 工具调用：支持选择牌阵、抽牌、解读、综合报告等工具
        5. 追问处理：结合占卜结果进行塔罗相关问题的追问回答
    
    使用场景：
        - 用户请求塔罗牌占卜
        - 用户对占卜结果进行追问
        - 用户切换到其他占卜话题
    
    ==============================================================================
    """

    @property
    def agent_id(self) -> str:
        """
        获取 Agent 唯一标识符
        
        Returns:
            str: Agent ID，固定返回 "tarot"
        """
        return "tarot"

    @property
    def display_name(self) -> str:
        """
        获取 Agent 显示名称
        
        Returns:
            str: Agent 显示名称，固定返回 "塔罗牌占卜"
        """
        return "塔罗牌占卜"

    @property
    def slot_schema(self) -> SlotSchema:
        """
        定义塔罗占卜所需的槽位模式
        
        槽位说明：
            - question_type: 问题类型（必填），匹配 "爱情"、"事业"、"财运"、"综合"、"健康"、"学业"、"人际关系"、"其他"
            - spread_type: 牌阵类型（可选），匹配 "单张"、"三张"、"凯尔特十字"、"五张"
            - specific_question: 具体问题（可选），匹配任意文本
        
        Returns:
            SlotSchema: 槽位模式定义对象
        """
        return SlotSchema({
            "question_type": {
                "required": True,
                "pattern": r"(爱情|事业|财运|综合|健康|学业|人际关系|其他)",
                "keywords": ["爱情", "事业", "财运", "综合", "健康", "学业", "人际关系", "其他"],
            },
            "spread_type": {
                "required": False,
                "pattern": r"(单张|三张|凯尔特十字|五张)",
                "keywords": ["单张", "三张", "凯尔特十字", "五张", "牌阵"],
            },
            "specific_question": {
                "required": False,
                "pattern": r".*",
                "keywords": ["问题", "想问", "关于", "想知道"],
            },
        })

    @property
    def intent_keywords(self) -> Dict[str, List[str]]:
        """
        定义五种意图类型的关键词
        
        意图类型：
            - NEW_ANALYSIS: 新的塔罗占卜请求
            - FOLLOW_UP: 追问（对当前占卜结果的进一步询问）
            - TOPIC_SWITCH: 话题切换
            - CLARIFICATION: 澄清请求（询问某个概念的含义）
            - GENERAL_QUERY: 通用查询（问候、感谢、再见等）
        
        Returns:
            Dict[str, List[str]]: 意图关键词映射字典
        """
        return {
            "NEW_ANALYSIS": [
                "塔罗", "占卜", "牌", "算牌", "抽牌", "塔罗牌", "塔罗占卜",
                "问塔罗", "塔罗预测", "塔罗解读", "帮我抽牌", "抽一张牌",
                "塔罗牌阵", "塔罗牌面",
            ],
            "FOLLOW_UP": [
                "这张牌", "解释一下", "什么意思", "代表什么",
                "为什么", "怎么理解", "详细说说",
                "牌面上", "这个符号", "那个图案",
            ],
            "TOPIC_SWITCH": [
                "换一个", "换个话题", "说说", "聊聊", "谈谈", "讲讲",
                "重新抽", "再抽一次", "换牌阵",
            ],
            "CLARIFICATION": [
                "什么意思", "为什么", "怎么", "如何", "哪个", "什么",
                "解释", "说明", "不清楚", "不明白",
            ],
            "GENERAL_QUERY": [
                "你好", "在吗", "谢谢", "感谢", "再见", "拜拜",
            ],
        }

    def get_domain_constraints(self) -> str:
        """
        获取塔罗占卜领域的约束条件
        
        Returns:
            str: 域约束字符串，用于限制 LLM 的回答范围
        """
        return TAROT_CONSTRAINTS

    async def handle_analysis(
        self,
        session: UnifiedSession,
        slots: Dict[str, Any],
        mode: str = "full",
    ) -> Dict[str, Any]:
        """
        ==============================================================================
        执行塔罗牌占卜 — ReAct Agent 模式
        ==============================================================================
        
        功能说明：
            处理用户的塔罗占卜请求，通过 LangGraph 的 ReAct Agent 模式
            驱动 LLM 自主决策调用工具完成占卜流程。
        
        参数说明：
            session (UnifiedSession): 会话上下文对象，包含用户信息和对话历史
            slots (Dict[str, Any]): 从用户输入中提取的槽位数据
            mode (str): 分析模式，目前固定为 "full"
        
        返回值：
            Dict[str, Any]: 占卜结果字典，包含：
                - response (str): 给用户的回复文本
                - output (Dict): 占卜输出数据
                - drawn_cards (List): 抽牌结果
                - graph_result (Dict): LangGraph 执行结果
        
        异常处理：
            捕获所有异常并返回友好的错误信息，避免程序崩溃
        
        执行流程：
            1. 检查必要槽位是否完整
            2. 构建初始 user message，让 LLM 理解任务
            3. 构建 LangGraph 输入
            4. 调用 LangGraph 执行占卜
            5. 返回占卜结果
        
        ==============================================================================
        """
        from src.graph.tarot_graph import tarot_app

        # 检查必要槽位是否完整
        missing = self.slot_schema.get_missing(slots)
        if missing:
            return {"response": "请告诉我您想占卜的方向（如：爱情、事业、财运、综合等）", "output": None}

        # 提取槽位数据
        question_type = slots.get("question_type", "综合")
        spread_type = slots.get("spread_type", "")
        specific_question = slots.get("specific_question", "")

        # 构建初始 user message，让 LLM 理解任务
        user_msg = f"用户想进行塔罗牌占卜。\n问题类型：{question_type}\n"
        if specific_question:
            user_msg += f"具体问题：{specific_question}\n"
        if spread_type:
            user_msg += f"用户指定牌阵：{spread_type}\n"
        else:
            user_msg += "用户未指定牌阵，请你根据问题自主选择合适的牌阵。\n"
        user_msg += "\n请开始占卜流程。"

        # 构建 LangGraph 输入
        graph_input = {
            "user_input": {
                "question_type": question_type,
                "spread_type": spread_type,
                "specific_question": specific_question,
            },
            "user_query": specific_question or f"{question_type}占卜",
            "messages": [{"role": "user", "content": user_msg}],
            "conversation_id": session.metadata.conversation_id,
            "user_id": session.metadata.user_id,
            "iteration": 0,  # 迭代计数器
            "pending_tool_calls": [],  # 待执行的工具调用
            "executor_state": {},  # 工具执行器状态
            "status": "initialized",
        }

        try:
            result = await tarot_app.ainvoke(graph_input)

            response = result.get("llm_response", "")
            if not response:
                response = "塔罗牌占卜完成，您可以继续追问了解更多。"

            return {
                "response": response,
                "output": result.get("tarot_result"),
                "drawn_cards": result.get("drawn_cards"),
                "graph_result": result,
            }
        except Exception as e:
            logger.error(f"塔罗牌占卜失败: {e}", exc_info=True)
            return {"response": f"占卜过程中出现错误: {str(e)}", "output": None}

    async def handle_followup(
        self,
        session: UnifiedSession,
        query: str,
    ) -> str:
        """
        ==============================================================================
        处理塔罗牌追问
        ==============================================================================
        
        功能说明：
            处理用户对塔罗占卜结果的追问，结合占卜结果生成回答。
        
        参数说明：
            session (UnifiedSession): 会话上下文对象，包含用户信息和对话历史
            query (str): 用户的追问文本
        
        返回值：
            str: 生成的追问回答
        
        执行流程：
            1. 构建塔罗上下文（提取占卜结果）
            2. 检查是否有占卜记录
            3. 使用 PromptRegistry 渲染提示词
            4. 调用 LLM 生成回答
        
        ==============================================================================
        """
        from src.dependencies import llm

        # 构建塔罗上下文：从 session 中提取占卜结果
        tarot_context = self._build_tarot_context(session)

        if not tarot_context:
            return "目前还没有占卜记录，请先进行一次塔罗牌占卜吧。"

        # 使用 PromptRegistry 渲染提示词
        prompt = PromptRegistry.render("tarot_follow_up", tarot_context=tarot_context, query=query)
        return await llm.acall(prompt)

    @staticmethod
    def _build_tarot_context(session: UnifiedSession) -> str:
        """
        ==============================================================================
        从 session 中提取塔罗占卜结果构建上下文
        ==============================================================================
        
        功能说明：
            从会话的塔罗缓存中提取占卜结果，格式化为 LLM 可理解的文本格式。
            包含牌阵信息、抽牌结果和综合解读。
        
        参数说明：
            session (UnifiedSession): 会话上下文对象
        
        返回值：
            str: 格式化的塔罗上下文文本
        
        格式示例：
            牌阵：凯尔特十字
        
            【抽牌结果】
            - 位置1: 意识（正位）
            - 位置2: 潜意识（逆位）
            
            【综合解读】
            [综合解读内容]
        
        ==============================================================================
        """
        if not session.tarot_cache:
            return ""

        cache = session.tarot_cache
        parts = []

        # 牌阵信息
        spread_info = cache.spread_info
        if spread_info:
            parts.append(f"牌阵：{spread_info.get('name_cn', '未知')}")

        # 抽牌结果
        if cache.drawn_cards:
            parts.append("\n【抽牌结果】")
            for card in cache.drawn_cards:
                # 将方向转换为中文
                orientation_cn = "正位" if card.get("orientation") == "upright" else "逆位"
                parts.append(f"- {card.get('position_name', '')}: {card.get('card_name_cn', '')}（{orientation_cn}）")

        # 综合解读
        if cache.synthesis:
            parts.append(f"\n【综合解读】\n{cache.synthesis[:3000]}")

        return "\n".join(parts)
