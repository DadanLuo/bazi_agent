"""
会话摘要模块
提供长对话自动摘要功能，减少 token 消耗
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

try:
    from src.llm.dashscope_llm import DashScopeLLM
    LLM_AVAILABLE = True
except ImportError:
    LLM_AVAILABLE = False
    DashScopeLLM = None

logger = logging.getLogger(__name__)


class ConversationSummarizer:
    """
    会话摘要器
    
    提供以下功能：
    - 自动摘要长对话
    - 保留关键信息
    - 减少 token 消耗
    """
    
    def __init__(self, llm: Optional[DashScopeLLM] = None):
        """
        初始化会话摘要器
        
        Args:
            llm: LLM 实例，如果为 None 尝试自动创建
        """
        self.llm = llm
        if llm is None and LLM_AVAILABLE:
            try:
                self.llm = DashScopeLLM()
                logger.info("✅ LLM 已自动初始化")
            except Exception as e:
                logger.warning(f"⚠️ LLM 初始化失败: {e}")
                self.llm = None
    
    def summarize_conversation(
        self,
        messages: List[Dict[str, str]],
        max_summary_length: int = 500,
        keep_latest: int = 5
    ) -> str:
        """
        摘要会话内容
        
        Args:
            messages: 消息列表，每条消息格式: {"role": "user/assistant", "content": "..."}
            max_summary_length: 最大摘要长度（字符数）
            keep_latest: 保留最近多少条消息不摘要
            
        Returns:
            摘要文本
        """
        if not messages:
            return ""
        
        # 分离需要摘要的消息和需要保留的消息
        if len(messages) > keep_latest:
            messages_to_summarize = messages[:-keep_latest]
            messages_to_keep = messages[-keep_latest:]
        else:
            messages_to_summarize = []
            messages_to_keep = messages
        
        # 如果没有需要摘要的消息
        if not messages_to_summarize:
            return ""
        
        # 构建摘要输入
        summary_input = self._build_summary_input(messages_to_summarize)
        
        # 生成摘要
        summary = self._generate_summary(summary_input, max_summary_length)
        
        return summary
    
    def _build_summary_input(self, messages: List[Dict[str, str]]) -> str:
        """
        构建摘要输入文本
        
        Args:
            messages: 消息列表
            
        Returns:
            摘要输入文本
        """
        input_text = ""
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            
            if role == "user":
                input_text += f"用户: {content}\n"
            elif role == "assistant":
                input_text += f"助手: {content}\n"
            else:
                input_text += f"{role}: {content}\n"
        
        return input_text
    
    def _generate_summary(self, input_text: str, max_length: int) -> str:
        """
        生成摘要
        
        Args:
            input_text: 输入文本
            max_length: 最大摘要长度
            
        Returns:
            摘要文本
        """
        if not self.llm:
            # 如果没有 LLM，返回简单的统计摘要
            return f"[系统自动摘要] 本次对话包含 {len(input_text)} 字符的对话内容。"
        
        # 构建摘要提示词
        prompt = f"""请将以下对话内容总结为简洁的要点，保留关键信息：

对话内容：
{input_text}

请用中文总结，不超过 {max_length} 字符，只返回摘要内容，不要添加其他文本。"""
        
        try:
            summary = self.llm.call(prompt)
            # 清理摘要文本
            summary = summary.strip().replace('"', '').replace("'", "")
            return summary[:max_length]
        except Exception as e:
            logger.error(f"摘要生成失败: {e}")
            return f"[系统自动摘要] 本次对话包含 {len(input_text)} 字符的对话内容。"
    
    def compress_conversation(
        self,
        messages: List[Dict[str, str]],
        summary_threshold: int = 10,
        keep_latest: int = 5
    ) -> List[Dict[str, str]]:
        """
        压缩会话（将长对话转换为摘要+最近消息）
        
        Args:
            messages: 消息列表
            summary_threshold: 摘要阈值（超过多少条消息进行摘要）
            keep_latest: 保留最近多少条消息
            
        Returns:
            压缩后的消息列表
        """
        if len(messages) < summary_threshold:
            return messages
        
        # 生成摘要
        summary = self.summarize_conversation(messages, keep_latest=keep_latest)
        
        if not summary:
            return messages
        
        # 构建压缩后的消息列表
        compressed_messages = []
        
        # 添加摘要消息
        compressed_messages.append({
            "role": "system",
            "content": f"【历史对话摘要】\n{summary}",
            "timestamp": datetime.now().isoformat()
        })
        
        # 添加保留的最近消息
        if len(messages) > keep_latest:
            compressed_messages.extend(messages[-keep_latest:])
        else:
            compressed_messages.extend(messages)
        
        return compressed_messages
    
    def get_conversation_stats(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        获取会话统计信息
        
        Args:
            messages: 消息列表
            
        Returns:
            统计信息字典
        """
        if not messages:
            return {
                "total_messages": 0,
                "user_messages": 0,
                "assistant_messages": 0,
                "total_chars": 0,
                "avg_message_length": 0
            }
        
        user_count = sum(1 for msg in messages if msg.get("role") == "user")
        assistant_count = sum(1 for msg in messages if msg.get("role") == "assistant")
        total_chars = sum(len(msg.get("content", "")) for msg in messages)
        
        return {
            "total_messages": len(messages),
            "user_messages": user_count,
            "assistant_messages": assistant_count,
            "total_chars": total_chars,
            "avg_message_length": total_chars // len(messages) if messages else 0
        }


class SessionMemoryCompressor:
    """
    会话内存压缩器
    
    结合摘要和上下文管理，实现高效的会话内存管理
    """
    
    def __init__(self, summarizer: Optional[ConversationSummarizer] = None):
        """
        初始化会话内存压缩器
        
        Args:
            summarizer: 摘要器实例
        """
        self.summarizer = summarizer or ConversationSummarizer()
    
    def compress_for_token_limit(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int,
        model_config: Any = None
    ) -> List[Dict[str, str]]:
        """
        根据 token 限制压缩会话
        
        Args:
            messages: 消息列表
            max_tokens: 最大 token 限制
            model_config: 模型配置
            
        Returns:
            压缩后的消息列表
        """
        # 获取会话统计
        stats = self.summarizer.get_conversation_stats(messages)
        logger.info(f"会话统计: {stats}")
        
        # 如果当前 token 使用在限制内，直接返回
        if stats["total_chars"] < max_tokens * 3:  # 粗略估算：1 token ≈ 3 字符
            return messages
        
        # 计算需要保留的消息数量
        keep_latest = max(3, len(messages) // 2)
        
        # 尝试压缩
        compressed = self.summarizer.compress_conversation(
            messages,
            keep_latest=keep_latest
        )
        
        # 检查压缩后的大小
        new_stats = self.summarizer.get_conversation_stats(compressed)
        
        if new_stats["total_chars"] > max_tokens * 3:
            # 如果仍然超过限制，进一步压缩
            return self.compress_for_token_limit(
                compressed,
                max_tokens,
                model_config
            )
        
        return compressed
    
    def create_summary_message(
        self,
        messages: List[Dict[str, str]],
        summary: str
    ) -> Dict[str, str]:
        """
        创建摘要消息
        
        Args:
            messages: 原始消息列表
            summary: 摘要文本
            
        Returns:
            摘要消息
        """
        return {
            "role": "system",
            "content": f"【历史对话摘要】\n{summary}",
            "timestamp": datetime.now().isoformat(),
            "original_message_count": len(messages)
        }


# 全局摘要器实例
summarizer = ConversationSummarizer()
session_compressor = SessionMemoryCompressor(summarizer)
