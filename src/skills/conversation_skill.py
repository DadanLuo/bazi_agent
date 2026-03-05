# src/skills/conversation_skill.py
"""对话管理技能 - 意图识别和槽位填充"""
from typing import Dict, Any, List, Optional
import re

from src.storage import SessionData, Message, MessageRole


class ConversationSkill:
    """对话管理技能类，支持意图识别和槽位填充"""
    
    # 意图类型定义
    INTENT_TYPES = {
        "NEW_ANALYSIS": "新分析请求",
        "FOLLOW_UP": "后续追问",
        "TOPIC_SWITCH": "话题切换",
        "CLARIFICATION": "澄清请求",
        "GENERAL_QUERY": "通用查询"
    }
    
    # 意图识别关键词
    INTENT_KEYWORDS = {
        "NEW_ANALYSIS": [
            "分析一下", "算一下", "看看", "命理", "八字", "运势", "命运",
            "生辰八字", "排盘", "解读", "预测", "测算"
        ],
        "FOLLOW_UP": [
            "那", "然后", "接着", "继续", "还有", "再", "另外", "此外",
            "关于这个", "那这个", "那那个", "具体", "详细", "进一步"
        ],
        "TOPIC_SWITCH": [
            "换一个", "换个话题", "说说", "聊聊", "谈谈", "讲讲", "关于",
            "另外", "此外", "还有", "再讲", "再聊"
        ],
        "CLARIFICATION": [
            "什么意思", "为什么", "怎么", "如何", "哪个", "什么", "为什么",
            "解释", "说明", "详细", "具体", "清楚", "明白"
        ],
        "GENERAL_QUERY": [
            "你好", "在吗", "在不在", "有人吗", "喂", "嗨", "嘿",
            "谢谢", "感谢", "多谢", "再见", "拜拜", "再见了"
        ]
    }
    
    # 槽位定义
    SLOTS = {
        "name": ["名字", "姓名", "称谓"],
        "gender": ["性别", "男", "女"],
        "birth_time": ["出生时间", "出生日期", "生日", "出生", "时间"],
        "birth_place": ["出生地", "地点", "城市", "地区", "地方"],
        "question": ["问题", "疑问", "困惑", "想知道", "请问"],
        "topic": ["话题", "主题", "说说", "聊聊", "谈谈"]
    }
    
    def __init__(self):
        """初始化对话技能"""
        self._current_intent = None
        self._current_slots = {}
    
    def detect_intent(self, user_query: str, session_data: Optional[SessionData] = None) -> Dict[str, Any]:
        """检测用户意图"""
        query_lower = user_query.lower()
        
        # 计算每个意图的匹配分数
        intent_scores = {}
        for intent_type, keywords in self.INTENT_KEYWORDS.items():
            score = 0
            for keyword in keywords:
                if keyword in query_lower:
                    score += 1
            intent_scores[intent_type] = score
        
        # 选择最高分的意图
        max_score = max(intent_scores.values())
        if max_score > 0:
            detected_intent = max(intent_scores, key=intent_scores.get)
        else:
            detected_intent = "GENERAL_QUERY"
        
        # 更新当前意图
        self._current_intent = detected_intent
        
        return {
            "intent": detected_intent,
            "intent_name": self.INTENT_TYPES.get(detected_intent, "未知意图"),
            "confidence": max_score / len(self.INTENT_KEYWORDS.get(detected_intent, [1])),
            "all_scores": intent_scores
        }
    
    def extract_slots(self, user_query: str) -> Dict[str, Any]:
        """提取槽位信息"""
        slots = {}
        
        for slot_name, keywords in self.SLOTS.items():
            for keyword in keywords:
                if keyword in user_query:
                    # 简单的槽位提取逻辑
                    slots[slot_name] = keyword
                    break
        
        # 更新当前槽位
        self._current_slots.update(slots)
        
        return slots
    
    def build_prompt_with_context(
        self,
        session_data: SessionData,
        user_query: str,
        context_text: str = "",
        intent_info: Optional[Dict[str, Any]] = None
    ) -> str:
        """构建带上下文的提示词"""
        messages = session_data.messages
        
        # 构建提示词
        prompt = ""
        
        # 添加系统提示词
        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                prompt += f"System: {msg.content}\n\n"
                break
        
        # 添加上下文
        if context_text:
            prompt += f"Context:\n{context_text}\n\n"
        
        # 添加意图信息
        if intent_info:
            prompt += f"Detected Intent: {intent_info.get('intent_name', 'Unknown')}\n\n"
        
        # 添加用户查询
        prompt += f"User: {user_query}\n\n"
        
        # 添加助手响应提示
        prompt += "Assistant: "
        
        return prompt
    
    def is_follow_up(self, user_query: str, session_data: Optional[SessionData] = None) -> bool:
        """判断是否为后续追问"""
        intent_info = self.detect_intent(user_query, session_data)
        return intent_info.get("intent") == "FOLLOW_UP"
    
    def is_topic_switch(self, user_query: str, session_data: Optional[SessionData] = None) -> bool:
        """判断是否为话题切换"""
        intent_info = self.detect_intent(user_query, session_data)
        return intent_info.get("intent") == "TOPIC_SWITCH"
    
    def is_new_analysis(self, user_query: str, session_data: Optional[SessionData] = None) -> bool:
        """判断是否为新分析请求"""
        intent_info = self.detect_intent(user_query, session_data)
        return intent_info.get("intent") == "NEW_ANALYSIS"
    
    def get_follow_up_response(self, previous_response: str, current_query: str) -> str:
        """生成后续追问响应"""
        return f"""基于之前的回答，您想了解什么？之前的回答是：
{previous_response}

您当前的问题是：
{current_query}

请基于之前的分析，详细回答用户的问题。"""
    
    def get_topic_switch_response(self, previous_topic: str, current_query: str) -> str:
        """生成话题切换响应"""
        return f"""我们之前讨论的是：{previous_topic}

现在您想聊：{current_query}

请自然地切换到新话题，继续提供有价值的分析和建议。"""
    
    def get_clarification_response(self, user_query: str) -> str:
        """生成澄清请求响应"""
        return f"""关于您的问题"{user_query}"，我需要更多信息来提供准确的分析。

请提供更多细节，例如：
- 具体的出生时间（年月日时）
- 出生地点
- 您关心的具体问题

我会根据您提供的信息进行详细分析。"""
    
    def reset(self) -> None:
        """重置对话状态"""
        self._current_intent = None
        self._current_slots = {}
    
    def get_current_state(self) -> Dict[str, Any]:
        """获取当前对话状态"""
        return {
            "current_intent": self._current_intent,
            "current_slots": self._current_slots
        }
    
    def update_state(self, intent: Optional[str] = None, slots: Optional[Dict[str, Any]] = None) -> None:
        """更新对话状态"""
        if intent:
            self._current_intent = intent
        if slots:
            self._current_slots.update(slots)
