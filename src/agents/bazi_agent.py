# src/agents/bazi_agent.py
"""
==============================================================================
八字 Agent — 八字命理分析核心组件
==============================================================================

功能说明：
    本模块实现了八字命理分析的 Agent，负责处理用户的八字排盘请求和后续追问。
    通过 LangGraph 工作流执行完整的八字分析流程，包括排盘、五行分析、格局判断、
    喜用神推导等步骤，并结合 RAG 知识检索和 LLM 生成分析报告。

主要职责：
    1. 槽位提取：从用户输入中提取出生年月日时、性别、出生地等必要信息
    2. 意图识别：识别用户意图（新分析、追问、话题切换、澄清等）
    3. 排盘分析：调用 LangGraph 执行完整的八字分析流程
    4. 缓存管理：使用 Redis 缓存已分析的八字结果，提高响应速度
    5. 追问处理：结合 RAG 检索和上下文进行八字相关问题的追问回答

使用场景：
    - 用户请求八字排盘分析
    - 用户对八字分析结果进行追问
    - 用户切换到其他命理咨询话题

==============================================================================
"""

import logging
from typing import Dict, Any, List

from src.agents.base import BaseAgent, SlotSchema
from src.core.contracts import UnifiedSession
from src.core.city_coords import resolve_city_coords
from src.prompts.registry import PromptRegistry, BAZI_CONSTRAINTS

logger = logging.getLogger(__name__)

# 性别映射表：将英文性别标识转换为中文
GENDER_TO_CHINESE = {"male": "男", "female": "女", "男": "男", "女": "女"}


class BaziAgent(BaseAgent):
    """
    ==============================================================================
    八字命理分析 Agent
    ==============================================================================
    
    功能说明：
        八字命理分析 Agent，负责处理用户的八字排盘请求和后续追问。
        继承自 BaseAgent，实现了八字分析领域的特定逻辑。
    
    核心特性：
        1. 槽位提取：定义了八字分析所需的槽位模式（出生年月日时、性别、地点）
        2. 意图识别：定义了五种意图类型的关键词（新分析、追问、话题切换、澄清、通用查询）
        3. 分析流程：通过 LangGraph 执行完整的八字分析流程
        4. 缓存机制：使用 Redis 缓存已分析的八字结果，提高响应速度
        5. 追问处理：结合 RAG 检索和上下文进行八字相关问题的追问回答
    
    使用场景：
        - 用户请求八字排盘分析
        - 用户对八字分析结果进行追问
        - 用户切换到其他命理咨询话题
    
    ==============================================================================
    """

    @property
    def agent_id(self) -> str:
        """
        获取 Agent 唯一标识符
        
        Returns:
            str: Agent ID，固定返回 "bazi"
        """
        return "bazi"

    @property
    def display_name(self) -> str:
        """
        获取 Agent 显示名称
        
        Returns:
            str: Agent 显示名称，固定返回 "八字命理分析"
        """
        return "八字命理分析"

    @property
    def slot_schema(self) -> SlotSchema:
        """
        定义八字分析所需的槽位模式
        
        槽位说明：
            - birth_year: 出生年份（必填），匹配格式如 "1990年"、"1990-"
            - birth_month: 出生月份（必填），匹配格式如 "5月"
            - birth_day: 出生日期（必填），匹配格式如 "15日"、"15号"
            - gender: 性别（必填），匹配 "男" 或 "女"
            - birth_hour: 出生时辰（可选），匹配格式如 "14点"、"14时"
            - birth_place: 出生地点（可选），匹配中文地名
        
        Returns:
            SlotSchema: 槽位模式定义对象
        """
        return SlotSchema({
            "birth_year": {"required": True, "pattern": r"(\d{4})[年\-]", "keywords": ["出生", "年份", "年"]},
            "birth_month": {"required": True, "pattern": r"(\d{1,2})[月]", "keywords": ["月"]},
            "birth_day": {"required": True, "pattern": r"(\d{1,2})[日号]", "keywords": ["日", "号"]},
            "gender": {"required": True, "pattern": r"(男|女)", "keywords": ["性别", "男", "女"]},
            "birth_hour": {"required": False, "pattern": r"(\d{1,2})(?:点|时)", "keywords": ["点", "时"]},
            "birth_place": {"required": False, "pattern": r"(?:出生地|地点|在)([\u4e00-\u9fa5]{2,})", "keywords": ["出生地", "城市"]},
        })

    @property
    def intent_keywords(self) -> Dict[str, List[str]]:
        """
        定义五种意图类型的关键词
        
        意图类型：
            - NEW_ANALYSIS: 新的八字分析请求
            - FOLLOW_UP: 追问（对当前分析结果的进一步询问）
            - TOPIC_SWITCH: 话题切换
            - CLARIFICATION: 澄清请求（询问某个概念的含义）
            - GENERAL_QUERY: 通用查询（问候、感谢、再见等）
        
        Returns:
            Dict[str, List[str]]: 意图关键词映射字典
        """
        return {
            "NEW_ANALYSIS": [
                "分析一下", "算一下", "看看", "命理", "八字", "运势", "命运",
                "生辰八字", "排盘", "解读", "预测", "测算",
            ],
            "FOLLOW_UP": [
                "那", "然后", "接着", "继续", "还有", "再", "另外", "此外",
                "关于这个", "那这个", "具体", "详细", "进一步",
            ],
            "TOPIC_SWITCH": [
                "换一个", "换个话题", "说说", "聊聊", "谈谈", "讲讲",
            ],
            "CLARIFICATION": [
                "什么意思", "为什么", "怎么", "如何", "哪个", "什么",
                "解释", "说明",
            ],
            "GENERAL_QUERY": [
                "你好", "在吗", "谢谢", "感谢", "再见",
            ],
        }

    def get_domain_constraints(self) -> str:
        """
        获取八字分析领域的约束条件
        
        Returns:
            str: 域约束字符串，用于限制 LLM 的回答范围
        """
        return BAZI_CONSTRAINTS

    async def handle_analysis(
        self,
        session: UnifiedSession,
        slots: Dict[str, Any],
        mode: str = "full",
    ) -> Dict[str, Any]:
        """
        ==============================================================================
        执行八字排盘分析
        ==============================================================================
        
        功能说明：
            处理用户的八字排盘请求，执行完整的八字分析流程。
            包括检查必要信息、调用 LangGraph 工作流、缓存结果等步骤。
        
        参数说明：
            session (UnifiedSession): 会话上下文对象，包含用户信息和对话历史
            slots (Dict[str, Any]): 从用户输入中提取的槽位数据
            mode (str): 分析模式，"full" 为完整分析，"simple" 为简单分析
        
        返回值：
            Dict[str, Any]: 分析结果字典，包含：
                - response (str): 给用户的回复文本
                - output (Dict): 分析输出数据（八字结果、分析报告等）
                - bazi_result (Dict): 原始八字排盘结果
                - graph_result (Dict): LangGraph 执行结果
        
        异常处理：
            捕获所有异常并返回友好的错误信息，避免程序崩溃
        
        执行流程：
            1. 检查必要槽位是否完整
            2. 构建 birth_info 字典（包含年月日时、性别、经纬度）
            3. 检查 Redis 缓存，命中则直接返回缓存结果
            4. 调用 LangGraph 执行八字分析
            5. 缓存分析结果到 Redis
            6. 返回分析结果
        
        ==============================================================================
        """
        from src.dependencies import redis_cache, llm
        from src.graph.bazi_graph import app as bazi_app
        from src.graph.simple_graph import simple_app

        # 检查必要槽位是否完整
        missing = self.slot_schema.get_missing(slots)
        if missing:
            # 将槽位键映射为中文名称
            slot_names = {"birth_year": "出生年", "birth_month": "出生月", "birth_day": "出生日", "gender": "性别"}
            desc = [slot_names.get(s, s) for s in missing]
            return {"response": f"还需要以下信息：{', '.join(desc)}", "output": None}

        # 构建 birth_info 字典
        gender_raw = slots.get("gender", "男")
        birth_info = {
            "year": slots.get("birth_year"),
            "month": slots.get("birth_month"),
            "day": slots.get("birth_day"),
            "hour": slots.get("birth_hour", 12),  # 默认为中午12点
            "gender": GENDER_TO_CHINESE.get(gender_raw, "男"),
        }
        # 如果已提供经纬度则直接使用，否则通过出生地解析
        if slots.get("longitude"):
            birth_info["longitude"] = slots["longitude"]
            birth_info["latitude"] = slots["latitude"]
        else:
            birth_place = slots.get("birth_place", "")
            coords = resolve_city_coords(birth_place)
            if coords:
                birth_info["longitude"] = coords[0]
                birth_info["latitude"] = coords[1]

        # 检查 Redis 缓存，命中则直接返回缓存结果
        if redis_cache:
            cached = redis_cache.get_bazi_result(birth_info)
            if cached and cached.get("bazi_result"):
                logger.info("命中八字 Redis 缓存")
                bazi_output = cached.get("final_report") or {}
                response = cached.get("llm_response", "") or bazi_output.get("report_text", "八字分析完成（缓存命中）。")
                return {"response": response, "output": bazi_output, "bazi_result": cached["bazi_result"]}

        # 构建 LangGraph 输入
        graph_input = {
            "user_input": birth_info,
            "status": "initialized",
            "user_id": session.metadata.user_id,
            "conversation_id": session.metadata.conversation_id,
        }

        try:
            # 根据模式选择不同的 Graph
            if mode == "simple":
                result = await simple_app.ainvoke(graph_input)
            else:
                result = await bazi_app.ainvoke(graph_input)

            bazi_output = None
            if result.get("bazi_result"):
                final_report = result.get("final_report")
                safe_output = result.get("safe_output")
                # 优先使用 final_report，其次使用 safe_output
                bazi_output = final_report if final_report else (safe_output if safe_output else None)

                # 回填 Redis 缓存
                if redis_cache:
                    redis_cache.cache_bazi_result(
                        birth_info=birth_info,
                        result={
                            "bazi_result": result.get("bazi_result"),
                            "final_report": bazi_output,
                            "llm_response": result.get("llm_response", ""),
                        },
                        ttl=7200,  # 缓存有效期 2 小时
                    )

            response = result.get("llm_response", "")
            if not response:
                if mode == "simple":
                    response = "八字排盘完成，您可以继续追问了解详细分析。"
                else:
                    report = result.get("final_report", {})
                    response = report.get("report_text", "八字分析完成。")

            return {
                "response": response,
                "output": bazi_output,
                "bazi_result": result.get("bazi_result"),
                "graph_result": result,
            }
        except Exception as e:
            logger.error(f"八字排盘失败: {e}", exc_info=True)
            return {"response": f"八字分析过程中出现错误: {str(e)}", "output": None}

    async def handle_followup(
        self,
        session: UnifiedSession,
        query: str,
    ) -> str:
        """
        ==============================================================================
        处理八字相关追问
        ==============================================================================
        
        功能说明：
            处理用户对八字分析结果的追问，结合 RAG 检索和上下文生成回答。
            支持会话摘要压缩、知识检索、上下文构建等功能。
        
        参数说明：
            session (UnifiedSession): 会话上下文对象，包含用户信息和对话历史
            query (str): 用户的追问文本
        
        返回值：
            str: 生成的追问回答
        
        执行流程：
            1. RAG 知识检索（使用 KnowledgeRetriever）
            2. 构建八字上下文（提取四柱数据）
            3. 构建对话历史上下文
            4. 使用 PromptRegistry 渲染提示词
            5. 调用 LLM 生成回答
        
        注意：
            已清理对不存在模块的引用（hybrid_retriever, context_skill, model_config, ConversationSummarizer）
        
        ==============================================================================
        """
        from src.dependencies import llm, retriever

        # RAG 检索：从知识库中检索相关命理知识
        retrieval_context = ""
        try:
            if retriever:
                docs = retriever.search(query, top_k=3)
                if docs:
                    retrieval_context = "\n【相关知识】\n" + "\n".join([
                        doc.get("content", "")[:500] for doc in docs[:3]
                    ])
        except Exception as e:
            logger.warning(f"RAG 检索失败: {e}")

        # 构建八字上下文：从 session 中提取四柱数据
        bazi_context = self._build_bazi_context(session)

        # 构建对话历史上下文（简化版，不使用 ConversationSummarizer）
        history_context = ""
        if session.messages:
            recent_messages = session.messages[-6:]  # 保留最近 6 条消息
            history_context = "\n【对话历史】\n" + "\n".join([
                f"{m.role}: {m.content[:200]}" for m in recent_messages
            ])

        # 使用 PromptRegistry 渲染提示词
        full_context = retrieval_context + bazi_context + history_context
        prompt = PromptRegistry.render("follow_up", context=full_context, query=query)

        if llm:
            return await llm.acall(prompt)
        else:
            return "抱歉，LLM 服务暂时不可用，请稍后再试。"

    # ---- 内部辅助方法 ----

    @staticmethod
    def _build_bazi_context(session: UnifiedSession) -> str:
        """
        ==============================================================================
        从 session 中提取四柱数据构建 LLM 上下文
        ==============================================================================
        
        功能说明：
            从会话的八字缓存中提取四柱八字数据，格式化为 LLM 可理解的文本格式。
            包含四柱干支和分析报告。
        
        参数说明：
            session (UnifiedSession): 会话上下文对象
        
        返回值：
            str: 格式化的八字上下文文本
        
        格式示例：
            【四柱八字】
            年柱: 甲子  月柱: 乙丑  日柱: 丙寅  时柱: 丁卯
            
            --- AI 分析报告 ---
            [分析报告内容]
        
        ==============================================================================
        """
        if not session.bazi_cache or not session.bazi_cache.bazi_data:
            return ""

        bazi_data = session.bazi_cache.bazi_data
        analysis_result = session.bazi_cache.analysis_result or {}

        bazi_info = ""
        if isinstance(bazi_data, dict):
            four_pillars = bazi_data.get("four_pillars", {})
            if four_pillars:
                bazi_info = "\n【四柱八字】\n"
                pillar_names = {"year": "年柱", "month": "月柱", "day": "日柱", "hour": "时柱"}
                for pname in ["year", "month", "day", "hour"]:
                    pillar = four_pillars.get(pname, {})
                    if isinstance(pillar, dict):
                        tg_raw = pillar.get("tiangan", "?")
                        dz_raw = pillar.get("dizhi", "?")
                        # 兼容 dict 和 str 两种格式
                        tg = tg_raw.get("value", tg_raw) if isinstance(tg_raw, dict) else str(tg_raw)
                        dz = dz_raw.get("value", dz_raw) if isinstance(dz_raw, dict) else str(dz_raw)
                    else:
                        tg, dz = "?", "?"
                    bazi_info += f"{pillar_names[pname]}: {tg}{dz}  "

        report_text = ""
        if isinstance(analysis_result, dict):
            report_text = analysis_result.get("llm_analysis", "") or analysis_result.get("report_text", "")

        result = f"\n\n--- 用户八字分析结果 ---\n{bazi_info}"
        if report_text:
            result += f"\n\n--- AI 分析报告 ---\n{report_text[:5000]}"
        return result

    # 注意：已移除 _build_context_compat 方法
    # 该方法依赖不存在的 ContextSkill 模块，现已直接在 handle_followup 中构建上下文
