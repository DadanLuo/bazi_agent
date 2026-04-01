# src/safety/review_queue.py
"""
==============================================================================
人工审核队列
==============================================================================

功能说明：
    本模块实现了人工审核队列，用于处理边界模糊内容的审核流程。
    当自动审核无法确定内容是否安全时，将内容加入人工审核队列，
    由人工审核员进行最终决策。

审核优先级：
    - HIGH: 心理危机、违法内容 - 立即处理
    - MEDIUM: 宿命论、迷信 - 尽快处理
    - LOW: 边界模糊内容 - 常规处理

审核状态：
    - PENDING: 待审核
    - APPROVED: 已批准
    - REJECTED: 已拒绝
    - EXPIRED: 已过期

==============================================================================
"""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Literal
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ReviewPriority(Enum):
    """
    ==============================================================================
    审核优先级
    ==============================================================================
    
    优先级说明：
        - HIGH: 心理危机、违法内容 - 立即处理
        - MEDIUM: 宿命论、迷信 - 尽快处理
        - LOW: 边界模糊内容 - 常规处理
    
    ==============================================================================
    """
    HIGH = "high"      # 心理危机、违法内容 - 立即处理
    MEDIUM = "medium"  # 宿命论、迷信 - 尽快处理
    LOW = "low"        # 边界模糊内容 - 常规处理


class ReviewStatus(Enum):
    """
    ==============================================================================
    审核状态
    ==============================================================================
    
    状态说明：
        - PENDING: 待审核
        - APPROVED: 已批准
        - REJECTED: 已拒绝
        - EXPIRED: 已过期
    
    ==============================================================================
    """
    PENDING = "pending"      # 待审核
    APPROVED = "approved"    # 已批准
    REJECTED = "rejected"    # 已拒绝
    EXPIRED = "expired"      # 已过期


@dataclass
class ReviewItem:
    """
    ==============================================================================
    审核项
    ==============================================================================
    
    属性说明：
        - id: 审核项唯一标识
        - content: 待审核内容
        - user_id: 用户ID
        - conversation_id: 会话ID
        - priority: 审核优先级
        - status: 审核状态
        - category: 安全类别
        - created_at: 创建时间
        - reviewed_at: 审核时间
        - reviewer_id: 审核员ID
        - review_note: 审核备注
        - original_action: 原始建议动作
    
    ==============================================================================
    """
    id: str
    content: str
    user_id: str
    conversation_id: str
    priority: ReviewPriority
    status: ReviewStatus = ReviewStatus.PENDING
    category: Optional[str] = None
    created_at: datetime = None
    reviewed_at: Optional[datetime] = None
    reviewer_id: Optional[str] = None
    review_note: Optional[str] = None
    original_action: Optional[str] = None  # 原始建议动作
    
    def __post_init__(self):
        """
        ==============================================================================
        初始化后处理
        ==============================================================================
        
        功能说明：
            如果创建时间未设置，则使用当前时间。
        
        ==============================================================================
        """
        if self.created_at is None:
            self.created_at = datetime.now()
    
    def to_dict(self) -> Dict:
        """
        ==============================================================================
        转换为字典格式
        ==============================================================================
        
        返回值：
            Dict: 审核项字典
        
        ==============================================================================
        """
        return {
            "id": self.id,
            "content": self.content,
            "user_id": self.user_id,
            "conversation_id": self.conversation_id,
            "priority": self.priority.value,
            "status": self.status.value,
            "category": self.category,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "reviewer_id": self.reviewer_id,
            "review_note": self.review_note,
            "original_action": self.original_action,
        }
    
    def to_json(self) -> str:
        """
        ==============================================================================
        转换为 JSON 字符串
        ==============================================================================
        
        返回值：
            str: JSON 字符串
        
        ==============================================================================
        """
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class ReviewQueue:
    """
    ==============================================================================
    人工审核队列
    ==============================================================================
    
    功能说明：
        人工审核队列，用于管理待审核的内容项。
        支持按优先级排队、持久化存储、过期清理等功能。
    
    核心方法：
        - add_item(): 添加审核项
        - get_next_item(): 获取下一个待审核项
        - get_pending_count(): 获取各队列待处理数量
        - approve_item(): 批准审核项
        - reject_item(): 拒绝审核项
        - get_item(): 获取审核项
        - get_all_pending(): 获取所有待审核项
        - cleanup_expired(): 清理过期审核项
    
    使用场景：
        - 边界模糊内容的人工审核
        - 高优先级内容的快速处理
        - 审核历史记录的持久化
    
    ==============================================================================
    """
    
    def __init__(self, storage_dir: str = "data/review_queue"):
        """
        ==============================================================================
        初始化人工审核队列
        ==============================================================================
        
        功能说明：
            初始化审核队列，加载已存在的审核项。
        
        参数说明：
            storage_dir (str): 审核项存储目录
        
        ==============================================================================
        """
        self.storage_dir = storage_dir
        self._queues: Dict[ReviewPriority, List[ReviewItem]] = {
            ReviewPriority.HIGH: [],
            ReviewPriority.MEDIUM: [],
            ReviewPriority.LOW: [],
        }
        self._items_by_id: Dict[str, ReviewItem] = {}
        
        # 创建存储目录
        os.makedirs(storage_dir, exist_ok=True)
        
        # 加载已存在的审核项
        self._load_existing_items()
    
    def _load_existing_items(self):
        """
        ==============================================================================
        加载已存在的审核项
        ==============================================================================
        
        功能说明：
            从存储目录加载已存在的审核项，恢复审核队列状态。
        
        ==============================================================================
        """
        if not os.path.exists(self.storage_dir):
            return
        
        for filename in os.listdir(self.storage_dir):
            if filename.endswith(".json"):
                filepath = os.path.join(self.storage_dir, filename)
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        item = ReviewItem(
                            id=data["id"],
                            content=data["content"],
                            user_id=data["user_id"],
                            conversation_id=data["conversation_id"],
                            priority=ReviewPriority(data["priority"]),
                            status=ReviewStatus(data["status"]),
                            category=data.get("category"),
                            created_at=datetime.fromisoformat(data["created_at"]),
                            reviewed_at=datetime.fromisoformat(data["reviewed_at"]) if data.get("reviewed_at") else None,
                            reviewer_id=data.get("reviewer_id"),
                            review_note=data.get("review_note"),
                            original_action=data.get("original_action"),
                        )
                        self._items_by_id[item.id] = item
                        self._queues[item.priority].append(item)
                except Exception as e:
                    logger.error(f"加载审核项失败: {filepath}, error: {e}")
    
    def add_item(
        self,
        content: str,
        user_id: str,
        conversation_id: str,
        priority: ReviewPriority,
        category: str = None,
        original_action: str = None,
    ) -> ReviewItem:
        """
        ==============================================================================
        添加审核项
        ==============================================================================
        
        功能说明：
            添加一个新的审核项到队列中。
        
        参数说明：
            content (str): 待审核内容
            user_id (str): 用户ID
            conversation_id (str): 会话ID
            priority (ReviewPriority): 审核优先级
            category (str): 安全类别（可选）
            original_action (str): 原始建议动作（可选）
        
        返回值：
            ReviewItem: 添加的审核项对象
        
        ==============================================================================
        """
        item = ReviewItem(
            id=f"review_{uuid.uuid4().hex[:8]}",
            content=content,
            user_id=user_id,
            conversation_id=conversation_id,
            priority=priority,
            category=category,
            original_action=original_action,
        )
        
        self._items_by_id[item.id] = item
        self._queues[priority].append(item)
        self._persist_item(item)
        
        logger.info(f"添加审核项: {item.id}, priority={priority.value}, category={category}")
        
        return item
    
    def get_next_item(self) -> Optional[ReviewItem]:
        """
        ==============================================================================
        获取下一个待审核项（优先处理高优先级）
        ==============================================================================
        
        功能说明：
            获取下一个待审核项，优先处理高优先级的内容。
        
        返回值：
            Optional[ReviewItem]: 下一个待审核项，如果没有则返回 None
        
        处理顺序：
            1. HIGH 优先级
            2. MEDIUM 优先级
            3. LOW 优先级
        
        ==============================================================================
        """
        for priority in [ReviewPriority.HIGH, ReviewPriority.MEDIUM, ReviewPriority.LOW]:
            queue = self._queues[priority]
            for item in queue:
                if item.status == ReviewStatus.PENDING:
                    return item
        return None
    
    def get_pending_count(self) -> Dict[str, int]:
        """
        ==============================================================================
        获取各队列待处理数量
        ==============================================================================
        
        返回值：
            Dict[str, int]: 各优先级队列的待处理数量
        
        ==============================================================================
        """
        return {
            priority.value: len([i for i in queue if i.status == ReviewStatus.PENDING])
            for priority, queue in self._queues.items()
        }
    
    def approve_item(
        self,
        item_id: str,
        reviewer_id: str = "system",
        note: str = None,
    ) -> bool:
        """
        ==============================================================================
        批准审核项
        ==============================================================================
        
        功能说明：
            批准一个审核项，将其状态设置为已批准。
        
        参数说明：
            item_id (str): 审核项ID
            reviewer_id (str): 审核员ID，默认为 "system"
            note (str): 审核备注（可选）
        
        返回值：
            bool: 是否批准成功
        
        ==============================================================================
        """
        item = self._items_by_id.get(item_id)
        if not item:
            return False
        
        item.status = ReviewStatus.APPROVED
        item.reviewed_at = datetime.now()
        item.reviewer_id = reviewer_id
        item.review_note = note
        self._persist_item(item)
        
        logger.info(f"批准审核项: {item_id}, reviewer={reviewer_id}")
        return True
    
    def reject_item(
        self,
        item_id: str,
        reviewer_id: str = "system",
        note: str = None,
    ) -> bool:
        """
        ==============================================================================
        拒绝审核项
        ==============================================================================
        
        功能说明：
            拒绝一个审核项，将其状态设置为已拒绝。
        
        参数说明：
            item_id (str): 审核项ID
            reviewer_id (str): 审核员ID，默认为 "system"
            note (str): 审核备注（可选）
        
        返回值：
            bool: 是否拒绝成功
        
        ==============================================================================
        """
        item = self._items_by_id.get(item_id)
        if not item:
            return False
        
        item.status = ReviewStatus.REJECTED
        item.reviewed_at = datetime.now()
        item.reviewer_id = reviewer_id
        item.review_note = note
        self._persist_item(item)
        
        logger.info(f"拒绝审核项: {item_id}, reviewer={reviewer_id}")
        return True
    
    def get_item(self, item_id: str) -> Optional[ReviewItem]:
        """
        ==============================================================================
        获取审核项
        ==============================================================================
        
        参数说明：
            item_id (str): 审核项ID
        
        返回值：
            Optional[ReviewItem]: 审核项对象，如果不存在则返回 None
        
        ==============================================================================
        """
        return self._items_by_id.get(item_id)
    
    def get_all_pending(self) -> List[ReviewItem]:
        """
        ==============================================================================
        获取所有待审核项
        ==============================================================================
        
        返回值：
            List[ReviewItem]: 所有待审核项列表
        
        ==============================================================================
        """
        pending = []
        for queue in self._queues.values():
            pending.extend([i for i in queue if i.status == ReviewStatus.PENDING])
        return pending
    
    def _persist_item(self, item: ReviewItem):
        """
        ==============================================================================
        持久化审核项
        ==============================================================================
        
        参数说明：
            item (ReviewItem): 审核项对象
        
        ==============================================================================
        """
        filepath = os.path.join(self.storage_dir, f"{item.id}.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(item.to_dict(), f, ensure_ascii=False, indent=2)
    
    def cleanup_expired(self, days: int = 7):
        """
        ==============================================================================
        清理过期的审核项
        ==============================================================================
        
        功能说明：
            清理超过指定天数的审核项，释放存储空间。
        
        参数说明：
            days (int): 过期天数，默认为 7 天
        
        ==============================================================================
        """
        cutoff = datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp() - (days * 86400)
        
        for item_id, item in list(self._items_by_id.items()):
            if item.created_at.timestamp() < cutoff:
                filepath = os.path.join(self.storage_dir, f"{item.id}.json")
                if os.path.exists(filepath):
                    os.remove(filepath)
                del self._items_by_id[item_id]
                for queue in self._queues.values():
                    if item in queue:
                        queue.remove(item)
        
        logger.info(f"清理过期审核项完成")


# 全局审核队列实例
review_queue = ReviewQueue()
