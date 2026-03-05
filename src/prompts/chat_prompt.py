# src/prompts/chat_prompt.py
"""多轮对话提示词 - 增强版"""

# 系统提示词
CHAT_SYSTEM_PROMPT = """
# Role
你是"赛博司命"，一位专业的八字命理分析助手。你正在与用户进行多轮对话。

# Context
{memory_context}

# 当前用户八字信息
{bazi_context}

# 对话规则
1. 如果用户追问细节，基于已缓存的八字数据进行深入分析
2. 如果用户切换话题（如流年、大运），使用缓存数据重新计算
3. 如果用户要求重新分析，提示需要提供新的出生信息
4. 保持回答专业、简洁，避免重复之前说过的内容
5. 保持上下文一致性，避免前后矛盾
6. 对用户的后续问题给予充分重视和详细解答

# 安全提醒
- 遇到心理危机信号，立即提供援助信息
- 避免宿命论表述，强调主观能动性
- 保持客观中立，不制造焦虑
"""

# 意图识别提示词
INTENT_DETECTION_PROMPT = """
请分析用户的意图类型：

用户问题：{user_query}

可选意图类型：
1. NEW_ANALYSIS - 新分析请求（用户首次请求或要求重新分析）
2. FOLLOW_UP - 后续追问（基于之前的分析提问）
3. TOPIC_SWITCH - 话题切换（想了解新的主题）
4. CLARIFICATION - 澄清请求（需要更详细的解释）
5. GENERAL_QUERY - 通用查询（问候、感谢等）

请返回意图类型和置信度分数（0-1）。
"""

# 意图响应模板
INTENT_RESPONSE_TEMPLATES = {
    "NEW_ANALYSIS": """好的，我将为您进行新的八字分析。请提供出生信息（年月日时）和性别，我将为您详细解读命理特点。""",
    "FOLLOW_UP": """好的，基于之前的分析，我来详细解答您的问题。""",
    "TOPIC_SWITCH": """好的，我们来聊一下{topic}。请稍等，我将基于您的八字信息进行分析。""",
    "CLARIFICATION": """好的，我来详细解释一下。""",
    "GENERAL_QUERY": """您好！我是您的八字命理助手，随时准备为您解答问题。"""
}

# 意图路由提示词
INTENT_ROUTER_PROMPT = """
# 意图路由规则

根据用户的意图，选择合适的处理流程：

1. NEW_ANALYSIS -> 跳转到分析节点，要求用户提供出生信息
2. FOLLOW_UP -> 使用缓存的八字数据进行深入分析
3. TOPIC_SWITCH -> 重新计算相关参数，进行新话题分析
4. CLARIFICATION -> 基于之前的分析，提供更详细的解释
5. GENERAL_QUERY -> 进行通用对话

用户问题：{user_query}

请返回意图类型和处理建议。
"""

# 槽位填充提示词
SLOT_FILLING_PROMPT = """
请从用户问题中提取槽位信息：

可提取槽位：
- name: 用户姓名
- gender: 性别（男/女）
- birth_time: 出生时间（年月日时）
- birth_place: 出生地点
- question: 具体问题
- topic: 话题主题

用户问题：{user_query}

请返回提取的槽位信息，格式为JSON。
"""

# 上下文构建提示词
CONTEXT_BUILDING_PROMPT = """
# 上下文构建规则

请根据用户的对话历史和当前问题，构建上下文：

1. 保留系统提示词
2. 保留关键的八字分析信息
3. 保留最近的对话历史（最多5轮）
4. 添加当前用户问题
5. 添加检索到的相关知识

上下文格式：
- System: 系统提示词
- User: 用户问题
- Assistant: 助手回答
- Context: 检索知识

请构建上下文文本。
"""

# 检索增强生成提示词
RAG_PROMPT = """
# 检索增强生成

请基于以下检索结果，回答用户问题：

检索结果：
{retrieval_results}

用户问题：{user_query}

请结合检索结果，提供专业、准确的回答。如果检索结果中没有相关信息，请基于您的专业知识进行回答。
"""

# 流程控制提示词
FLOW_CONTROL_PROMPT = """
# 流程控制

请根据当前状态，决定下一步操作：

当前状态：
- 意图：{intent}
- 槽位：{slots}
- 上下文：{context}

可选操作：
1. REQUEST_INFO - 请求用户补充信息
2. RETRIEVE_KNOWLEDGE - 检索相关知识
3. GENERATE_RESPONSE - 生成回答
4. SWITCH_TOPIC - 切换话题
5. CLARIFY - 进行澄清

请返回操作类型和相关参数。
"""

# 多轮对话状态管理提示词
STATE_MANAGEMENT_PROMPT = """
# 多轮对话状态管理

请维护对话状态：

当前状态：
- 对话轮数：{turn_count}
- 最近意图：{recent_intents}
- 槽位填充情况：{slot_filling}
- 用户满意度：{user_satisfaction}

请更新状态并决定下一步操作。
"""

# 对话结束提示词
CONVERSATION_END_PROMPT = """
# 对话结束

用户表示对话结束，请生成结束语：

用户输入：{user_input}

请生成友好的结束语，感谢用户的咨询。
"""

# 对话质量评估提示词
QUALITY_ASSESSMENT_PROMPT = """
# 对话质量评估

请评估助手的回答质量：

评估维度：
1. 相关性：回答是否针对用户问题
2. 准确性：内容是否准确专业
3. 完整性：回答是否完整
4. 专业性：是否体现专业水平
5. 可读性：是否易于理解

请给出每个维度的评分（1-5分）和总体评价。
"""
