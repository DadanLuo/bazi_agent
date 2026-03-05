"""
模型配置管理
支持动态切换模型，自动调整上下文窗口
"""
from typing import Dict, Any

# 模型配置字典
MODEL_CONFIGS: Dict[str, Dict[str, Any]] = {
    "qwen-plus": {
        "context_window": 128000,      # 12.8万 token
        "max_output": 6000,
        "supports_streaming": True,
    },
    "qwen-turbo": {
        "context_window": 128000,
        "max_output": 6000,
        "supports_streaming": True,
    },
    "qwen-long": {
        "context_window": 1000000,     # 100万 token
        "max_output": 10000,
        "supports_streaming": True,
    },
    "deepseek-v3": {
        "context_window": 64000,
        "max_output": 8000,
        "supports_streaming": True,
    },
    "qwen-max": {
        "context_window": 32000,
        "max_output": 8000,
        "supports_streaming": True,
    },
}


class ModelConfig:
    """动态模型配置管理"""
    
    def __init__(self, model_name: str = "qwen-plus"):
        """
        初始化模型配置
        
        Args:
            model_name: 模型名称，默认为 qwen-plus
        """
        self.config = MODEL_CONFIGS.get(model_name, MODEL_CONFIGS["qwen-plus"])
        self.model_name = model_name
        
    @property
    def context_window(self) -> int:
        """获取上下文窗口大小"""
        return self.config["context_window"]
    
    @property
    def max_output(self) -> int:
        """获取最大输出 token 数"""
        return self.config["max_output"]
    
    @property
    def supports_streaming(self) -> bool:
        """是否支持流式输出"""
        return self.config.get("supports_streaming", False)
    
    def get_max_history_tokens(self, reserve_ratio: float = 0.3) -> int:
        """
        获取最大历史 token 数（预留输出空间）
        
        Args:
            reserve_ratio: 预留比例（用于输出），默认 0.3
            
        Returns:
            最大历史 token 数
        """
        return int(self.context_window * (1 - reserve_ratio))
    
    def get_max_history_messages(self, reserve_ratio: float = 0.3) -> int:
        """
        获取最大历史消息数（基于经验估算）
        
        Args:
            reserve_ratio: 预留比例，默认 0.3
            
        Returns:
            最大消息数
        """
        # 经验估算：每轮对话约 1000-2000 tokens
        avg_tokens_per_message = 1500
        max_history_tokens = self.get_max_history_tokens(reserve_ratio)
        return max(1, max_history_tokens // avg_tokens_per_message)
    
    def __repr__(self) -> str:
        return f"ModelConfig(model_name={self.model_name}, context_window={self.context_window})"


def get_model_config(model_name: str = "qwen-plus") -> ModelConfig:
    """
    获取模型配置实例
    
    Args:
        model_name: 模型名称
        
    Returns:
        ModelConfig 实例
    """
    return ModelConfig(model_name)


# 默认配置
default_config = ModelConfig()
