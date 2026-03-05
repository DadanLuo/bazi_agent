# src/skills/context_skill.py
"""上下文管理技能 - 支持多种上下文策略"""
from typing import Dict, Any, List, Optional
from datetime import datetime

from src.storage import SessionData, Message, MessageRole
from src.config.model_config import ModelConfig
from src.config.rag_config import RAGConfigManager


class ContextSkill:
    """上下文管理技能类，支持多种上下文策略"""
    
    def __init__(self, model_config: Optional[ModelConfig] = None):
        """初始化上下文技能"""
        self.model_config = model_config or ModelConfig()
        self.rag_config = RAGConfigManager
    
    def build_context(
        self,
        session_data: SessionData,
        user_query: str,
        retrieval_results: Optional[List[Dict[str, Any]]] = None,
        max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """构建上下文（根据策略）"""
        strategy = session_data.metadata.context_strategy
        
        if strategy == "FULL_CONTEXT":
            return self._build_full_context(session_data, user_query, retrieval_results, max_tokens)
        elif strategy == "SLIDING_WINDOW":
            return self._build_sliding_window_context(session_data, user_query, retrieval_results, max_tokens)
        elif strategy == "HYBRID":
            return self._build_hybrid_context(session_data, user_query, retrieval_results, max_tokens)
        else:
            return self._build_full_context(session_data, user_query, retrieval_results, max_tokens)
    
    def _build_full_context(
        self,
        session_data: SessionData,
        user_query: str,
        retrieval_results: Optional[List[Dict[str, Any]]] = None,
        max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """全量上下文策略"""
        messages = session_data.messages
        
        # 构建上下文文本
        context_text = ""
        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                context_text += f"System: {msg.content}\n\n"
            elif msg.role == MessageRole.USER:
                context_text += f"User: {msg.content}\n\n"
            elif msg.role == MessageRole.ASSISTANT:
                context_text += f"Assistant: {msg.content}\n\n"
        
        # 添加检索结果
        if retrieval_results:
            context_text += "\n--- 检索知识 ---\n"
            for i, result in enumerate(retrieval_results):
                context_text += f"[{i+1}] {result.get('content', '')}\n\n"
        
        # 添加当前用户查询
        context_text += f"Current Query: {user_query}\n"
        
        # 计算 token 使用
        token_count = self._estimate_tokens(context_text)
        
        return {
            "context_text": context_text,
            "token_count": token_count,
            "strategy": "FULL_CONTEXT",
            "messages_used": len(messages),
            "retrieval_results_count": len(retrieval_results) if retrieval_results else 0
        }
    
    def _build_sliding_window_context(
        self,
        session_data: SessionData,
        user_query: str,
        retrieval_results: Optional[List[Dict[str, Any]]] = None,
        max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """滑动窗口策略"""
        messages = session_data.messages
        
        # 计算最大历史 token
        if max_tokens is None:
            max_tokens = self.model_config.get_max_history_tokens()
        
        # 保留系统提示词
        system_message = messages[0] if messages and messages[0].role == MessageRole.SYSTEM else None
        
        # 从后往前构建滑动窗口
        window_messages = []
        current_tokens = 0
        
        # 从最近的消息开始
        for msg in reversed(messages[1:]):  # 跳过系统提示词
            msg_tokens = self._estimate_tokens(msg.content)
            
            # 检查是否超过限制
            if current_tokens + msg_tokens > max_tokens:
                break
            
            window_messages.insert(0, msg)
            current_tokens += msg_tokens
        
        # 构建上下文文本
        context_text = ""
        if system_message:
            context_text += f"System: {system_message.content}\n\n"
        
        for msg in window_messages:
            if msg.role == MessageRole.USER:
                context_text += f"User: {msg.content}\n\n"
            elif msg.role == MessageRole.ASSISTANT:
                context_text += f"Assistant: {msg.content}\n\n"
        
        # 添加检索结果
        if retrieval_results:
            context_text += "\n--- 检索知识 ---\n"
            for i, result in enumerate(retrieval_results):
                context_text += f"[{i+1}] {result.get('content', '')}\n\n"
        
        # 添加当前用户查询
        context_text += f"Current Query: {user_query}\n"
        
        # 估算总 token
        total_tokens = current_tokens + self._estimate_tokens(context_text)
        
        return {
            "context_text": context_text,
            "token_count": total_tokens,
            "strategy": "SLIDING_WINDOW",
            "messages_used": len(window_messages),
            "retrieval_results_count": len(retrieval_results) if retrieval_results else 0,
            "max_tokens": max_tokens
        }
    
    def _build_hybrid_context(
        self,
        session_data: SessionData,
        user_query: str,
        retrieval_results: Optional[List[Dict[str, Any]]] = None,
        max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """混合策略：保留关键消息 + 最近消息"""
        messages = session_data.messages
        
        # 计算最大历史 token
        if max_tokens is None:
            max_tokens = self.model_config.get_max_history_tokens()
        
        # 保留系统提示词
        system_message = messages[0] if messages and messages[0].role == MessageRole.SYSTEM else None
        
        # 提取关键消息（包含八字分析）
        key_messages = []
        recent_messages = []
        
        for msg in messages[1:]:  # 跳过系统提示词
            content = msg.content.lower()
            if any(keyword in content for keyword in ["八字", "命理", "分析", "喜用神", "格局"]):
                key_messages.append(msg)
            else:
                recent_messages.append(msg)
        
        # 构建上下文文本
        context_text = ""
        if system_message:
            context_text += f"System: {system_message.content}\n\n"
        
        # 添加关键消息
        for msg in key_messages:
            if msg.role == MessageRole.USER:
                context_text += f"User: {msg.content}\n\n"
            elif msg.role == MessageRole.ASSISTANT:
                context_text += f"Assistant: {msg.content}\n\n"
        
        # 添加最近消息（在 token 限制内）
        current_tokens = self._estimate_tokens(context_text)
        for msg in recent_messages[-10:]:  # 最多10条最近消息
            msg_tokens = self._estimate_tokens(msg.content)
            if current_tokens + msg_tokens > max_tokens:
                break
            if msg.role == MessageRole.USER:
                context_text += f"User: {msg.content}\n\n"
            elif msg.role == MessageRole.ASSISTANT:
                context_text += f"Assistant: {msg.content}\n\n"
            current_tokens += msg_tokens
        
        # 添加检索结果
        if retrieval_results:
            context_text += "\n--- 检索知识 ---\n"
            for i, result in enumerate(retrieval_results):
                context_text += f"[{i+1}] {result.get('content', '')}\n\n"
        
        # 添加当前用户查询
        context_text += f"Current Query: {user_query}\n"
        
        # 估算总 token
        total_tokens = current_tokens + self._estimate_tokens(context_text)
        
        return {
            "context_text": context_text,
            "token_count": total_tokens,
            "strategy": "HYBRID",
            "messages_used": len(key_messages) + min(10, len(recent_messages)),
            "retrieval_results_count": len(retrieval_results) if retrieval_results else 0,
            "max_tokens": max_tokens
        }
    
    def _estimate_tokens(self, text: str) -> int:
        """估算 token 数量（经验公式：1 token ≈ 3-4 字符）"""
        if not text:
            return 0
        return len(text) // 3  # 粗略估算
    
    def check_context_length(
        self,
        context_text: str,
        max_context_ratio: float = 0.7
    ) -> Dict[str, Any]:
        """检查上下文长度"""
        total_tokens = self._estimate_tokens(context_text)
        max_history_tokens = self.model_config.get_max_history_tokens()
        max_context_tokens = int(max_history_tokens * max_context_ratio)
        
        return {
            "total_tokens": total_tokens,
            "max_context_tokens": max_context_tokens,
            "exceeded": total_tokens > max_context_tokens,
            "ratio": total_tokens / max_context_tokens if max_context_tokens > 0 else 0
        }
    
    def generate_summary(
        self,
        messages: List[Message],
        summary_prompt: Optional[str] = None
    ) -> str:
        """生成消息摘要（用于长上下文压缩）"""
        if not messages:
            return ""
        
        # 构建待摘要的消息文本
        summary_input = ""
        for msg in messages[-10:]:  # 最多10条消息
            if msg.role == MessageRole.USER:
                summary_input += f"User: {msg.content}\n"
            elif msg.role == MessageRole.ASSISTANT:
                summary_input += f"Assistant: {msg.content}\n"
        
        # 默认摘要提示词
        if not summary_prompt:
            summary_prompt = f"""请将以下对话内容总结为简洁的要点，保留关键信息：

{summary_input}

请用中文总结，不超过100字。"""
        
        return summary_prompt