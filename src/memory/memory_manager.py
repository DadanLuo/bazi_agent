"""
多轮对话 Memory 管理器
支持上下文记忆和多轮追问
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    Memory 管理器

    功能：
    1. 存储对话历史
    2. 提取关键信息（八字数据、分析结果）
    3. 生成上下文提示词
    """

    def __init__(self, storage_path: str = "data/memory"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # 内存缓存
        self._cache: Dict[str, Dict] = {}

    def create_conversation(self, user_id: str = "default") -> str:
        """
        创建新对话

        Returns:
            conversation_id
        """
        import uuid
        conv_id = f"{user_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

        self._cache[conv_id] = {
            "conversation_id": conv_id,
            "user_id": user_id,
            "created_at": datetime.now().isoformat(),
            "messages": [],
            "bazi_data": None,  # 存储八字核心数据
            "analysis_summary": None  # 存储分析摘要
        }

        logger.info(f"创建新对话: {conv_id}")
        return conv_id

    def add_message(self, conversation_id: str, role: str, content: str):
        """
        添加消息到对话历史

        Args:
            conversation_id: 对话ID
            role: "user" 或 "assistant"
            content: 消息内容
        """
        if conversation_id not in self._cache:
            logger.warning(f"对话不存在: {conversation_id}")
            return

        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }

        self._cache[conversation_id]["messages"].append(message)

        # 持久化（可选）
        self._save_to_disk(conversation_id)

    def store_bazi_data(self, conversation_id: str, bazi_data: Dict):
        """
        存储八字核心数据，用于后续追问
        """
        if conversation_id not in self._cache:
            logger.warning(f"对话不存在: {conversation_id}")
            return

        self._cache[conversation_id]["bazi_data"] = bazi_data
        self._save_to_disk(conversation_id)

    def get_conversation_history(self, conversation_id: str,
                                 max_messages: int = 10) -> List[Dict]:
        """
        获取对话历史

        Args:
            conversation_id: 对话ID
            max_messages: 最大消息数

        Returns:
            消息列表 [{"role": ..., "content": ...}, ...]
        """
        if conversation_id not in self._cache:
            # 尝试从磁盘加载
            self._load_from_disk(conversation_id)

        if conversation_id not in self._cache:
            return []

        messages = self._cache[conversation_id].get("messages", [])

        # 返回最近的消息
        return messages[-max_messages:]

    def generate_memory_context(self, conversation_id: str) -> str:
        """
        生成记忆上下文，用于LLM提示词

        Returns:
            格式化的上下文字符串
        """
        if conversation_id not in self._cache:
            self._load_from_disk(conversation_id)

        if conversation_id not in self._cache:
            return ""

        conv = self._cache[conversation_id]

        context_parts = []

        # 1. 八字核心信息
        if conv.get("bazi_data"):
            bazi = conv["bazi_data"]
            context_parts.append("【用户八字信息】")
            context_parts.append(f"四柱：{bazi.get('four_pillars', '未知')}")
            context_parts.append(f"格局：{bazi.get('geju', '未知')}")
            context_parts.append(f"喜用神：{bazi.get('yongshen', '未知')}")
            context_parts.append("")

        # 2. 最近对话摘要
        messages = conv.get("messages", [])
        if messages:
            context_parts.append("【最近对话】")
            for msg in messages[-5:]:  # 最近5轮
                role = "用户" if msg["role"] == "user" else "助手"
                context_parts.append(f"{role}: {msg['content'][:100]}...")  # 截断
            context_parts.append("")

        return "\n".join(context_parts)

    def _save_to_disk(self, conversation_id: str):
        """持久化到磁盘"""
        try:
            filepath = self.storage_path / f"{conversation_id}.json"
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self._cache[conversation_id], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存对话失败: {e}")

    def _load_from_disk(self, conversation_id: str) -> bool:
        """从磁盘加载"""
        try:
            filepath = self.storage_path / f"{conversation_id}.json"
            if filepath.exists():
                with open(filepath, "r", encoding="utf-8") as f:
                    self._cache[conversation_id] = json.load(f)
                return True
        except Exception as e:
            logger.error(f"加载对话失败: {e}")
        return False

    def clear_conversation(self, conversation_id: str):
        """清除对话"""
        if conversation_id in self._cache:
            del self._cache[conversation_id]

        # 删除文件
        filepath = self.storage_path / f"{conversation_id}.json"
        if filepath.exists():
            filepath.unlink()


# 全局单例
memory_manager = MemoryManager()
