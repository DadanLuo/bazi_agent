# src/skills/base.py
"""Skill 基类和标准输出定义"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime


@dataclass
class SkillResult:
    """Skill 执行结果"""
    success: bool
    data: Dict[str, Any]
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "metadata": self.metadata
        }
    
    @classmethod
    def success_result(cls, data: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> "SkillResult":
        """创建成功结果"""
        return cls(success=True, data=data, metadata=metadata or {})
    
    @classmethod
    def error_result(cls, error: str, metadata: Optional[Dict[str, Any]] = None) -> "SkillResult":
        """创建错误结果"""
        return cls(success=False, data={}, error=error, metadata=metadata or {})


class BaseSkill(ABC):
    """Skill 基类，所有 Skill 应继承此类"""
    
    def __init__(self):
        """初始化 Skill"""
        self._created_at = datetime.now()
    
    @property
    def name(self) -> str:
        """技能名称 - 子类应覆盖此属性"""
        return self.__class__.__name__
    
    @property
    def description(self) -> str:
        """技能描述 - 子类应覆盖此属性"""
        return self.__doc__ or "无描述"
    
    @property
    def version(self) -> str:
        """技能版本"""
        return "1.0.0"
    
    @property
    def created_at(self) -> datetime:
        """创建时间"""
        return self._created_at
    
    @property
    def input_schema(self) -> Dict[str, Any]:
        """输入参数 Schema (JSON Schema 格式) - 子类可覆盖"""
        return {}
    
    @abstractmethod
    def execute(
        self, 
        input_data: Dict[str, Any], 
        context: Optional[Dict[str, Any]] = None
    ) -> SkillResult:
        """执行技能 - 子类必须实现
        
        Args:
            input_data: 输入数据字典
            context: 上下文信息（可选）
            
        Returns:
            SkillResult: 执行结果
        """
        pass
    
    def validate_input(self, input_data: Dict[str, Any]) -> bool:
        """验证输入参数 - 子类可覆盖以实现自定义验证"""
        # 默认实现：检查是否为字典
        return isinstance(input_data, dict)
    
    def run(
        self, 
        input_data: Dict[str, Any], 
        context: Optional[Dict[str, Any]] = None
    ) -> SkillResult:
        """运行技能（带输入验证）"""
        if not self.validate_input(input_data):
            return SkillResult.error_result(
                error="输入参数格式错误，应为字典类型",
                metadata={"input_type": type(input_data).__name__}
            )
        return self.execute(input_data, context)
    
    def __call__(
        self, 
        input_data: Dict[str, Any], 
        context: Optional[Dict[str, Any]] = None
    ) -> SkillResult:
        """支持直接调用"""
        return self.run(input_data, context)
    
    def get_info(self) -> Dict[str, Any]:
        """获取 Skill 信息"""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "created_at": self.created_at.isoformat(),
            "input_schema": self.input_schema
        }
