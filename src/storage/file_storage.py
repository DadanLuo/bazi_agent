# src/storage/file_storage.py
"""
文件存储管理器 - 旧版实现，用于向后兼容
"""

import json
import gzip
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
import logging

from .models import SessionData, StorageConfig
from src.core.contracts import UnifiedSession

logger = logging.getLogger(__name__)


class FileStorage:
    """
    文件存储管理器 - 旧版实现
    用于向后兼容，将 SessionData 保存到文件
    """

    def __init__(self, config: Optional[StorageConfig] = None):
        self.config = config or StorageConfig()
        self.storage_path = Path(self.config.storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def save_session(self, session_data: SessionData) -> bool:
        """
        保存会话数据到文件
        
        Args:
            session_data: 会话数据
            
        Returns:
            bool: 是否保存成功
        """
        try:
            # 转换 datetime 对象为 isoformat 字符串
            session_dict = session_data.model_dump()
            
            # 处理 datetime 对象的序列化
            if 'metadata' in session_dict and 'created_at' in session_dict['metadata']:
                session_dict['metadata']['created_at'] = session_dict['metadata']['created_at'].isoformat()
            if 'metadata' in session_dict and 'updated_at' in session_dict['metadata']:
                session_dict['metadata']['updated_at'] = session_dict['metadata']['updated_at'].isoformat()
            if session_dict.get('bazi_cache') and 'timestamp' in session_dict['bazi_cache']:
                session_dict['bazi_cache']['timestamp'] = session_dict['bazi_cache']['timestamp'].isoformat()

            file_path = self.storage_path / f"{session_data.conversation_id}.json"
            
            if self.config.compression:
                with gzip.open(file_path, 'wt', encoding='utf-8') as f:
                    json.dump(session_dict, f, ensure_ascii=False, indent=2)
            else:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(session_dict, f, ensure_ascii=False, indent=2)
            
            logger.debug(f"会话数据已保存: {session_data.conversation_id}")
            return True
        except Exception as e:
            logger.error(f"保存会话失败: {e}")
            return False

    def save_unified_session(self, session: UnifiedSession) -> bool:
        """
        保存 UnifiedSession 到文件
        """
        try:
            session_dict = session.model_dump(mode="json")
            file_path = self.storage_path / f"{session.metadata.conversation_id}.json"

            if self.config.compression:
                with gzip.open(file_path, 'wt', encoding='utf-8') as f:
                    json.dump(session_dict, f, ensure_ascii=False, indent=2)
            else:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(session_dict, f, ensure_ascii=False, indent=2)

            logger.debug(f"UnifiedSession 已保存: {session.metadata.conversation_id}")
            return True
        except Exception as e:
            logger.error(f"保存 UnifiedSession 失败: {e}")
            return False

    def load_session(self, conversation_id: str) -> Optional[SessionData]:
        """
        从文件加载会话数据
        
        Args:
            conversation_id: 会话ID
            
        Returns:
            SessionData: 会话数据，如果不存在则返回None
        """
        try:
            file_path = self.storage_path / f"{conversation_id}.json"
            
            if not file_path.exists():
                return None
            
            # 读取数据
            if self.config.compression:
                with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                    session_dict = json.load(f)
            else:
                with open(file_path, 'r', encoding='utf-8') as f:
                    session_dict = json.load(f)
            
            # 反序列化 datetime
            if session_dict.get('metadata', {}).get('created_at'):
                session_dict['metadata']['created_at'] = datetime.fromisoformat(session_dict['metadata']['created_at'])
            if session_dict.get('metadata', {}).get('updated_at'):
                session_dict['metadata']['updated_at'] = datetime.fromisoformat(session_dict['metadata']['updated_at'])
            if session_dict.get('bazi_cache', {}).get('timestamp'):
                session_dict['bazi_cache']['timestamp'] = datetime.fromisoformat(session_dict['bazi_cache']['timestamp'])
            
            return SessionData(**session_dict)
        except Exception as e:
            logger.error(f"加载会话失败: {e}")
            return None

    def load_unified_session(self, conversation_id: str) -> Optional[UnifiedSession]:
        """
        从文件加载 UnifiedSession
        """
        try:
            file_path = self.storage_path / f"{conversation_id}.json"

            if not file_path.exists():
                return None

            if self.config.compression:
                with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                    session_dict = json.load(f)
            else:
                with open(file_path, 'r', encoding='utf-8') as f:
                    session_dict = json.load(f)

            return UnifiedSession.model_validate(session_dict)
        except Exception as e:
            logger.warning(f"加载 UnifiedSession 失败，尝试旧格式回退: {e}")
            return None

    def delete_session(self, conversation_id: str) -> bool:
        """
        删除会话文件
        
        Args:
            conversation_id: 会话ID
            
        Returns:
            bool: 是否删除成功
        """
        try:
            file_path = self.storage_path / f"{conversation_id}.json"
            if file_path.exists():
                file_path.unlink()
                logger.debug(f"会话文件已删除: {conversation_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"删除会话失败: {e}")
            return False

    def list_sessions(self) -> list:
        """
        列出所有会话文件
        
        Returns:
            list: 会话ID列表
        """
        try:
            sessions = []
            pattern = "*.json.gz" if self.config.compression else "*.json"
            for file_path in self.storage_path.glob(pattern):
                session_id = file_path.stem
                sessions.append(session_id)
            return sessions
        except Exception as e:
            logger.error(f"列出会话失败: {e}")
            return []

    def clear_all_sessions(self) -> bool:
        """
        清空所有会话文件
        
        Returns:
            bool: 是否清空成功
        """
        try:
            sessions = self.list_sessions()
            for session_id in sessions:
                self.delete_session(session_id)
            logger.info(f"已清空 {len(sessions)} 个会话文件")
            return True
        except Exception as e:
            logger.error(f"清空会话失败: {e}")
            return False


__all__ = ["FileStorage"]
