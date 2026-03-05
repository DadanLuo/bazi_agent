# src/rag/reranker.py
"""重排序模块 - 使用 BGE-Reranker"""
from typing import Dict, Any, List, Optional
import time
import threading

from src.config.rag_config import RAGConfigManager


class Reranker:
    """重排序器，使用 BGE-Reranker-v2-m3 模型"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """初始化重排序器"""
        self.config = config or RAGConfigManager.get_rerank_config()
        self.model_name = self.config.get("model", "bge-reranker-v2-m3")
        self.top_k = self.config.get("top_k", 5)
        
        # API调用限制配置
        api_limit = self.config.get("api_limit", {})
        self.calls_per_5_hours = api_limit.get("calls_per_5_hours", 1200)
        self.cooldown_seconds = api_limit.get("cooldown_seconds", 15)
        
        # 调用计数器
        self._call_count = 0
        self._window_start_time = time.time()
        self._lock = threading.Lock()
    
    def _check_rate_limit(self) -> bool:
        """检查API调用限制"""
        with self._lock:
            current_time = time.time()
            
            # 检查是否超过5小时窗口
            if current_time - self._window_start_time > 5 * 3600:  # 5小时
                self._window_start_time = current_time
                self._call_count = 0
            
            # 检查是否超过调用限制
            if self._call_count >= self.calls_per_5_hours:
                return False
            
            self._call_count += 1
            return True
    
    def _wait_for_cooldown(self) -> None:
        """等待冷却时间"""
        with self._lock:
            if self._call_count >= self.calls_per_5_hours:
                # 计算需要等待的时间
                elapsed = time.time() - self._window_start_time
                wait_time = (5 * 3600) - elapsed + self.cooldown_seconds
                if wait_time > 0:
                    time.sleep(min(wait_time, 60))  # 最多等待60秒
    
    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """重排序文档"""
        if top_k is None:
            top_k = self.top_k
        
        # 检查API调用限制
        if not self._check_rate_limit():
            # 如果超过限制，返回原始排序的前K个
            return documents[:top_k]
        
        # 等待冷却
        self._wait_for_cooldown()
        
        # 模拟重排序（实际应调用 BGE-Reranker API）
        # 这里使用简单的相关性分数排序
        results = []
        for doc in documents:
            content = doc.get("content", "")
            score = doc.get("score", 0)
            
            # 简单的相关性评分（实际应使用 BGE-Reranker）
            # 这里假设 score 已经是相关性分数
            results.append({
                "content": content,
                "score": score,
                "metadata": doc.get("metadata", {})
            })
        
        # 按分数排序
        results.sort(key=lambda x: x["score"], reverse=True)
        
        return results[:top_k]
    
    def rerank_with_pairs(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """使用查询-文档对进行重排序"""
        if top_k is None:
            top_k = self.top_k
        
        # 检查API调用限制
        if not self._check_rate_limit():
            return documents[:top_k]
        
        # 等待冷却
        self._wait_for_cooldown()
        
        # 模拟重排序
        results = []
        for doc in documents:
            content = doc.get("content", "")
            score = doc.get("score", 0)
            
            results.append({
                "content": content,
                "score": score,
                "metadata": doc.get("metadata", {})
            })
        
        # 按分数排序
        results.sort(key=lambda x: x["score"], reverse=True)
        
        return results[:top_k]
    
    def get_call_count(self) -> int:
        """获取当前窗口内的调用次数"""
        with self._lock:
            return self._call_count
    
    def get_remaining_calls(self) -> int:
        """获取剩余调用次数"""
        with self._lock:
            return max(0, self.calls_per_5_hours - self._call_count)
    
    def reset_call_count(self) -> None:
        """重置调用计数器"""
        with self._lock:
            self._call_count = 0
            self._window_start_time = time.time()
    
    def get_status(self) -> Dict[str, Any]:
        """获取重排序器状态"""
        with self._lock:
            elapsed = time.time() - self._window_start_time
            return {
                "model": self.model_name,
                "top_k": self.top_k,
                "call_count": self._call_count,
                "remaining_calls": max(0, self.calls_per_5_hours - self._call_count),
                "calls_per_5_hours": self.calls_per_5_hours,
                "window_elapsed_seconds": elapsed,
                "window_remaining_seconds": max(0, 5 * 3600 - elapsed)
            }