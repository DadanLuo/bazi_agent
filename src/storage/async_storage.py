# src/storage/async_storage.py
"""
==============================================================================
异步存储管理器
==============================================================================

功能说明：
    本模块实现了异步存储管理器，支持批量写入和异步持久化。
    通过后台工作线程实现异步写入，减少请求响应时间。

核心功能：
    1. 异步写入文件，减少请求响应时间
    2. 批量写入，减少磁盘 I/O
    3. 支持强制刷新
    4. 支持会话数据的增删查改

==============================================================================
"""

import asyncio
import logging
import threading
import queue
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from .models import SessionData, StorageConfig, Message, BaziCache

logger = logging.getLogger(__name__)


class AsyncStorageManager:
    """
    ==============================================================================
    异步存储管理器
    ==============================================================================
    
    功能说明：
        异步存储管理器，支持批量写入和异步持久化。
        通过后台工作线程实现异步写入，减少请求响应时间。
    
    核心特性：
        1. 异步写入：使用后台线程处理文件写入
        2. 批量写入：积累多个写入请求后批量处理
        3. 强制刷新：支持立即刷新所有待写入数据
        4. 压缩存储：可选的 gzip 压缩
    
    核心方法：
        - start(): 启动异步写入线程
        - stop(): 停止异步写入线程
        - save_session_async(): 异步保存会话数据
        - save_session_sync(): 同步保存会话数据
        - load_session(): 加载会话数据
        - flush(): 强制刷新所有待写入数据
        - delete_session(): 删除会话数据
        - list_sessions(): 列出所有会话
        - clear_all_sessions(): 清空所有会话
    
    使用场景：
        - 会话数据持久化
        - 批量数据写入
        - 高并发场景下的异步存储
    
    ==============================================================================
    """
    
    def __init__(self, storage_path: str = "data/memory", compression: bool = True):
        """
        ==============================================================================
        初始化异步存储管理器
        ==============================================================================
        
        功能说明：
            初始化异步存储管理器，配置存储路径和压缩选项。
        
        参数说明：
            storage_path (str): 存储路径，默认为 "data/memory"
            compression (bool): 是否启用压缩，默认为 True
        
        ==============================================================================
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.compression = compression
        
        # 写入队列
        self._write_queue = queue.Queue(maxsize=1000)
        
        # 后台工作线程
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False
        
        # 批量写入配置
        self._batch_size = 10
        self._flush_interval = 5  # 秒
        
        # 最近写入时间
        self._last_write_time = datetime.now()
    
    def start(self):
        """
        ==============================================================================
        启动异步写入线程
        ==============================================================================
        
        功能说明：
            启动后台工作线程，开始异步处理写入队列中的任务。
        
        ==============================================================================
        """
        if self._running:
            return
        
        self._running = True
        self._worker_thread = threading.Thread(target=self._write_worker, daemon=True)
        self._worker_thread.start()
        logger.info("异步存储管理器已启动")
    
    def stop(self, timeout: float = 5.0):
        """
        ==============================================================================
        停止异步写入线程
        ==============================================================================
        
        功能说明：
            停止后台工作线程，并强制刷新剩余数据。
        
        参数说明：
            timeout (float): 等待线程停止的超时时间（秒）
        
        ==============================================================================
        """
        if not self._running:
            return
        
        self._running = False
        
        if self._worker_thread:
            self._worker_thread.join(timeout=timeout)
        
        # 强制刷新剩余数据
        self.flush()
        
        logger.info("异步存储管理器已停止")
    
    def save_session_async(self, session_data: SessionData) -> bool:
        """
        ==============================================================================
        异步保存会话数据
        ==============================================================================
        
        功能说明：
            将会话数据加入写入队列，由后台线程异步处理。
        
        参数说明：
            session_data (SessionData): 会话数据
        
        返回值：
            bool: 是否成功加入队列
        
        异常处理：
            - 队列已满时，降级为同步写入
        
        ==============================================================================
        """
        try:
            self._write_queue.put_nowait(("save", session_data))
            return True
        except queue.Full:
            logger.warning("写入队列已满，尝试同步写入")
            return self._sync_save(session_data)
    
    def save_session_sync(self, session_data: SessionData) -> bool:
        """
        ==============================================================================
        同步保存会话数据
        ==============================================================================
        
        功能说明：
            立即同步保存会话数据到文件。
        
        参数说明：
            session_data (SessionData): 会话数据
        
        返回值：
            bool: 是否保存成功
        
        ==============================================================================
        """
        return self._sync_save(session_data)
    
    def load_session(self, conversation_id: str) -> Optional[SessionData]:
        """
        ==============================================================================
        加载会话数据
        ==============================================================================
        
        功能说明：
            从文件中加载指定会话的数据。
        
        参数说明：
            conversation_id (str): 会话ID
        
        返回值：
            Optional[SessionData]: 会话数据，失败返回 None
        
        ==============================================================================
        """
        try:
            file_path = self.storage_path / f"{conversation_id}.json"
            
            if not file_path.exists():
                return None
            
            # 读取数据
            if self.compression:
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
            logger.error(f"加载会话失败: {e}")
            return None
    
    def flush(self):
        """
        ==============================================================================
        强制刷新所有待写入数据
        ==============================================================================
        
        功能说明：
            立即处理写入队列中的所有待写入数据。
        
        ==============================================================================
        """
        while not self._write_queue.empty():
            try:
                task = self._write_queue.get_nowait()
                if task:
                    action, data = task
                    if action == "save":
                        self._sync_save(data)
            except queue.Empty:
                break
    
    def _write_worker(self):
        """
        ==============================================================================
        后台写入线程
        ==============================================================================
        
        功能说明：
            后台工作线程，负责处理写入队列中的任务。
            支持批量写入和定时刷新。
        
        批量写入策略：
            1. 队列中任务数量达到 _batch_size 时刷新
            2. 距离上次刷新时间超过 _flush_interval 时刷新
        
        ==============================================================================
        """
        batch = []
        
        while self._running:
            try:
                # 从队列获取任务
                task = self._write_queue.get(timeout=1)
                if task:
                    batch.append(task)
                
                # 检查是否需要刷新
                if len(batch) >= self._batch_size:
                    self._process_batch(batch)
                    batch = []
                
                # 检查是否超时刷新
                if batch and (datetime.now() - self._last_write_time).total_seconds() >= self._flush_interval:
                    self._process_batch(batch)
                    batch = []
                    
            except queue.Empty:
                # 队列为空，检查是否有待处理的批处理
                if batch:
                    self._process_batch(batch)
                    batch = []
                continue
            except Exception as e:
                logger.error(f"写入线程错误: {e}")
    
    def _process_batch(self, batch: List[tuple]):
        """
        ==============================================================================
        处理批处理任务
        ==============================================================================
        
        参数说明：
            batch (List[tuple]): 批处理任务列表
        
        ==============================================================================
        """
        for action, data in batch:
            if action == "save":
                self._sync_save(data)
        self._last_write_time = datetime.now()
    
    def _sync_save(self, session_data: SessionData) -> bool:
        """
        ==============================================================================
        同步保存会话数据
        ==============================================================================
        
        功能说明：
            将会话数据同步保存到文件。
        
        参数说明：
            session_data (SessionData): 会话数据
        
        返回值：
            bool: 是否保存成功
        
        保存格式：
            - JSON 格式
            - 可选 gzip 压缩
            - datetime 对象序列化为 ISO 格式字符串
        
        ==============================================================================
        """
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
            if self.compression:
                import gzip
                file_path = self.storage_path / f"{session_data.conversation_id}.json"
                with gzip.open(file_path, 'wt', encoding='utf-8') as f:
                    json.dump(session_dict, f, ensure_ascii=False, indent=2)
            else:
                file_path = self.storage_path / f"{session_data.conversation_id}.json"
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(session_dict, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception as e:
            logger.error(f"保存会话失败: {e}")
            return False
    
    def delete_session(self, conversation_id: str) -> bool:
        """
        ==============================================================================
        删除会话数据
        ==============================================================================
        
        功能说明：
            从文件中删除指定会话的数据。
        
        参数说明：
            conversation_id (str): 会话ID
        
        返回值：
            bool: 是否删除成功
        
        ==============================================================================
        """
        try:
            file_path = self.storage_path / f"{conversation_id}.json"
            if file_path.exists():
                file_path.unlink()
            return True
        except Exception as e:
            logger.error(f"删除会话失败: {e}")
            return False
    
    def list_sessions(self, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        ==============================================================================
        列出所有会话
        ==============================================================================
        
        功能说明：
            列出所有会话的元数据信息。
        
        参数说明：
            user_id (Optional[str]): 用户ID（可选），如果提供则只返回该用户的会话
        
        返回值：
            List[Dict[str, Any]]: 会话列表，按更新时间降序排列
        
        ==============================================================================
        """
        sessions = []
        try:
            for file_path in self.storage_path.glob("*.json"):
                if self.compression:
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
            logger.error(f"列出会话失败: {e}")
        
        # 按更新时间排序
        sessions.sort(key=lambda x: x['updated_at'], reverse=True)
        return sessions
    
    def clear_all_sessions(self) -> bool:
        """
        ==============================================================================
        清空所有会话
        ==============================================================================
        
        功能说明：
            删除所有会话数据文件。
        
        返回值：
            bool: 是否清空成功
        
        ==============================================================================
        """
        try:
            for file_path in self.storage_path.glob("*.json"):
                file_path.unlink()
            return True
        except Exception as e:
            logger.error(f"清空会话失败: {e}")
            return False
    
    def get_queue_size(self) -> int:
        """
        ==============================================================================
        获取队列大小
        ==============================================================================
        
        返回值：
            int: 写入队列中的任务数量
        
        ==============================================================================
        """
        return self._write_queue.qsize()


# 全局单例
async_storage_manager = AsyncStorageManager()
