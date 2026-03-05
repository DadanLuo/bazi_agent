# src/storage/file_storage.py
"""文件存储实现"""
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from .models import SessionData, StorageConfig, Message, BaziCache


class FileStorage:
    """文件存储实现类"""
    
    def __init__(self, config: Optional[StorageConfig] = None):
        """初始化文件存储"""
        self.config = config or StorageConfig()
        self.storage_path = Path(self.config.storage_path)
        self.bm25_index_path = Path(self.config.bm25_index_path)
        
        # 创建存储目录
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.bm25_index_path.mkdir(parents=True, exist_ok=True)
    
    def _get_conversation_path(self, conversation_id: str) -> Path:
        """获取会话文件路径"""
        return self.storage_path / f"{conversation_id}.json"
    
    def save_session(self, session_data: SessionData) -> bool:
        """保存会话数据"""
        try:
            session_dict = session_data.model_dump(mode='json')
            
            # 序列化 datetime
            if session_dict.get('metadata', {}).get('created_at'):
                session_dict['metadata']['created_at'] = session_dict['metadata']['created_at'].isoformat()
            if session_dict.get('metadata', {}).get('updated_at'):
                session_dict['metadata']['updated_at'] = session_dict['metadata']['updated_at'].isoformat()
            if session_dict.get('bazi_cache', {}).get('timestamp'):
                session_dict['bazi_cache']['timestamp'] = session_dict['bazi_cache']['timestamp'].isoformat()
            
            # 压缩数据（可选）
            if self.config.compression:
                import gzip
                content = json.dumps(session_dict, ensure_ascii=False, indent=2)
                with gzip.open(self._get_conversation_path(session_data.conversation_id), 'wt', encoding='utf-8') as f:
                    f.write(content)
            else:
                with open(self._get_conversation_path(session_data.conversation_id), 'w', encoding='utf-8') as f:
                    json.dump(session_dict, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception as e:
            print(f"Error saving session: {e}")
            return False
    
    def load_session(self, conversation_id: str) -> Optional[SessionData]:
        """加载会话数据"""
        try:
            file_path = self._get_conversation_path(conversation_id)
            
            if not file_path.exists():
                return None
            
            # 读取数据
            if self.config.compression:
                import gzip
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
            print(f"Error loading session: {e}")
            return None
    
    def delete_session(self, conversation_id: str) -> bool:
        """删除会话数据"""
        try:
            file_path = self._get_conversation_path(conversation_id)
            if file_path.exists():
                file_path.unlink()
            return True
        except Exception as e:
            print(f"Error deleting session: {e}")
            return False
    
    def list_sessions(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出所有会话"""
        sessions = []
        try:
            for file_path in self.storage_path.glob("*.json"):
                if self.config.compression:
                    import gzip
                    with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                        session_dict = json.load(f)
                else:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        session_dict = json.load(f)
                
                # 只获取元数据
                metadata = session_dict.get('metadata', {})
                if user_id is None or metadata.get('user_id') == user_id:
                    sessions.append({
                        'conversation_id': metadata.get('conversation_id'),
                        'user_id': metadata.get('user_id'),
                        'message_count': metadata.get('message_count', 0),
                        'created_at': metadata.get('created_at', datetime.now()).isoformat() if hasattr(metadata.get('created_at'), 'isoformat') else metadata.get('created_at'),
                        'updated_at': metadata.get('updated_at', datetime.now()).isoformat() if hasattr(metadata.get('updated_at'), 'isoformat') else metadata.get('updated_at')
                    })
        except Exception as e:
            print(f"Error listing sessions: {e}")
        
        # 按更新时间排序
        sessions.sort(key=lambda x: x['updated_at'], reverse=True)
        return sessions
    
    def save_bm25_index(self, index_data: Dict[str, Any]) -> bool:
        """保存 BM25 索引"""
        try:
            index_file = self.bm25_index_path / "bm25_index.json"
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Error saving BM25 index: {e}")
            return False
    
    def load_bm25_index(self) -> Optional[Dict[str, Any]]:
        """加载 BM25 索引"""
        try:
            index_file = self.bm25_index_path / "bm25_index.json"
            if not index_file.exists():
                return None
            with open(index_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading BM25 index: {e}")
            return None
    
    def clear_all_sessions(self) -> bool:
        """清空所有会话"""
        try:
            for file_path in self.storage_path.glob("*.json"):
                file_path.unlink()
            return True
        except Exception as e:
            print(f"Error clearing sessions: {e}")
            return False