# src/skills/memory_skill.py
"""记忆管理技能 - 支持 OpenAI 标准消息格式"""
from typing import Dict, Any, List, Optional
from datetime import datetime

from src.storage import FileStorage, SessionData, Message, MessageRole, StorageConfig
from src.config.model_config import ModelConfig


class MemorySkill:
    """记忆管理技能类，支持 OpenAI 标准消息格式"""
    
    def __init__(self, storage: Optional[FileStorage] = None, model_config: Optional[ModelConfig] = None):
        """初始化记忆技能"""
        self.storage = storage or FileStorage()
        self.model_config = model_config or ModelConfig()
        self._current_session: Optional[SessionData] = None
    
    def create_session(
        self,
        conversation_id: str,
        user_id: str = "default",
        session_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        context_strategy: str = "FULL_CONTEXT",
        retrieval_mode: str = "hybrid_rerank"
    ) -> SessionData:
        """创建新会话"""
        # 创建会话数据
        session_data = SessionData(
            conversation_id=conversation_id,
            user_id=user_id,
            messages=[],
            metadata={
                "session_id": session_id,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
                "message_count": 0,
                "token_count": 0,
                "context_strategy": context_strategy,
                "retrieval_mode": retrieval_mode
            }
        )
        
        # 添加系统提示词
        if system_prompt:
            session_data.add_message(MessageRole.SYSTEM, system_prompt)
        
        # 保存会话
        self.storage.save_session(session_data)
        self._current_session = session_data
        
        return session_data
    
    def load_session(self, conversation_id: str) -> Optional[SessionData]:
        """加载会话"""
        session_data = self.storage.load_session(conversation_id)
        if session_data:
            self._current_session = session_data
        return session_data
    
    def get_current_session(self) -> Optional[SessionData]:
        """获取当前会话"""
        return self._current_session
    
    def add_user_message(self, content: str) -> bool:
        """添加用户消息"""
        if not self._current_session:
            return False
        self._current_session.add_message(MessageRole.USER, content)
        self._update_session()
        return True
    
    def add_assistant_message(self, content: str) -> bool:
        """添加助手消息"""
        if not self._current_session:
            return False
        self._current_session.add_message(MessageRole.ASSISTANT, content)
        self._update_session()
        return True
    
    def add_system_message(self, content: str) -> bool:
        """添加系统消息"""
        if not self._current_session:
            return False
        self._current_session.add_message(MessageRole.SYSTEM, content)
        self._update_session()
        return True
    
    def _update_session(self) -> None:
        """更新会话"""
        if self._current_session:
            self._current_session.metadata.updated_at = datetime.now()
            self.storage.save_session(self._current_session)
    
    def get_messages(self) -> List[Message]:
        """获取所有消息"""
        if not self._current_session:
            return []
        return self._current_session.messages
    
    def get_openai_format(self) -> List[Dict[str, str]]:
        """获取 OpenAI 标准格式消息"""
        if not self._current_session:
            return []
        return self._current_session.get_openai_format()
    
    def get_alpaca_format(self) -> Dict[str, Any]:
        """获取 Alpaca 格式消息"""
        if not self._current_session:
            return {"conversations": [], "system": ""}
        return self._current_session.get_alpaca_format()
    
    def get_context_messages(self, max_tokens: Optional[int] = None) -> List[Message]:
        """获取上下文消息（根据策略）"""
        if not self._current_session:
            return []
        
        strategy = self._current_session.metadata.context_strategy
        
        if strategy == "FULL_CONTEXT":
            # 全量上下文
            return self._current_session.messages
        elif strategy == "SLIDING_WINDOW":
            # 滑动窗口策略
            return self._get_sliding_window_messages(max_tokens)
        elif strategy == "HYBRID":
            # 混合策略
            return self._get_hybrid_messages(max_tokens)
        else:
            return self._current_session.messages
    
    def _get_sliding_window_messages(self, max_tokens: Optional[int] = None) -> List[Message]:
        """滑动窗口策略：保留最近的消息"""
        if not self._current_session:
            return []
        
        messages = self._current_session.messages
        if not messages:
            return []
        
        # 保留系统提示词和最近的消息
        result = [messages[0]]  # 保留系统提示词
        
        # 计算最大消息数（经验估算）
        max_history_messages = self.model_config.get_max_history_messages()
        
        # 只保留最近的消息
        if len(messages) > max_history_messages:
            result.extend(messages[-max_history_messages:])
        else:
            result.extend(messages)
        
        return result
    
    def _get_hybrid_messages(self, max_tokens: Optional[int] = None) -> List[Message]:
        """混合策略：保留重要消息 + 最近消息"""
        if not self._current_session:
            return []
        
        messages = self._current_session.messages
        if not messages:
            return []
        
        result = [messages[0]]  # 保留系统提示词
        
        # 提取包含八字分析的关键消息
        key_messages = []
        for msg in messages[1:]:  # 跳过系统提示词
            content = msg.content.lower()
            if any(keyword in content for keyword in ["八字", "命理", "分析", "喜用神"]):
                key_messages.append(msg)
        
        # 保留关键消息和最近消息
        result.extend(key_messages)
        
        # 添加最近的消息（排除已添加的关键消息）
        recent_messages = messages[-5:]  # 最近5条
        for msg in recent_messages:
            if msg not in key_messages:
                result.append(msg)
        
        return result
    
    def clear_session(self) -> bool:
        """清空会话"""
        if not self._current_session:
            return False
        self._current_session.messages = []
        self._current_session.metadata.message_count = 0
        self._current_session.metadata.token_count = 0
        self._current_session.metadata.updated_at = datetime.now()
        self.storage.save_session(self._current_session)
        return True
    
    def export_for_finetuning(self, format_type: str = "openai") -> List[Dict[str, Any]]:
        """导出微调数据"""
        if not self._current_session:
            return []
        
        if format_type == "alpaca":
            return [self._current_session.get_alpaca_format()]
        else:
            # OpenAI 格式
            messages = self._current_session.get_openai_format()
            return [{"messages": messages}]
    
    def update_bazi_cache(self, bazi_data: Dict[str, Any], analysis_result: Dict[str, Any]) -> bool:
        """更新八字缓存"""
        if not self._current_session:
            return False
        
        self._current_session.bazi_cache = BaziCache(
            bazi_data=bazi_data,
            analysis_result=analysis_result,
            timestamp=datetime.now()
        )
        self._update_session()
        return True
    
    def get_bazi_cache(self) -> Optional[BaziCache]:
        """获取八字缓存"""
        if not self._current_session:
            return None
        return self._current_session.bazi_cache
