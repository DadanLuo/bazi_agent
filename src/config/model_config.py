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


class ContextStrategySelector:
    """
    上下文策略自动选择器
    
    根据查询类型和模型配置自动选择最优的上下文策略：
    - FULL_CONTEXT: 全量上下文（大窗口模型）
    - SLIDING_WINDOW: 滑动窗口（小窗口模型）
    - HYBRID: 混合策略（摘要+窗口）
    """
    
    # 查询类型与推荐策略映射
    QUERY_STRATEGY_MAP = {
        "NEW_ANALYSIS": "FULL_CONTEXT",      # 新八字分析 - 需要完整上下文
        "FOLLOW_UP": "HYBRID",               # 追问 - 混合策略
        "GENERAL_CHAT": "SLIDING_WINDOW",    # 一般聊天 - 滑动窗口
        "DETAILED_EXPLANATION": "FULL_CONTEXT",  # 详细解释 - 全量上下文
        "SUMMARY_REQUEST": "HYBRID",         # 摘要请求 - 混合策略
    }
    
    # 模型推荐策略
    MODEL_STRATEGY_MAP = {
        "qwen-plus": "HYBRID",       # 中等窗口 - 混合策略
        "qwen-turbo": "SLIDING_WINDOW",  # 小窗口 - 滑动窗口
        "qwen-long": "FULL_CONTEXT",     # 大窗口 - 全量上下文
        "deepseek-v3": "HYBRID",         # 中等窗口 - 混合策略
        "qwen-max": "HYBRID",            # 中等窗口 - 混合策略
    }
    
    @classmethod
    def select_strategy(
        cls,
        query_type: str = "GENERAL_CHAT",
        model_name: str = "qwen-plus",
        message_count: int = 0,
        max_messages: int = 50
    ) -> str:
        """
        自动选择上下文策略
        
        Args:
            query_type: 查询类型
            model_name: 模型名称
            message_count: 当前消息数量
            max_messages: 最大消息数阈值
            
        Returns:
            推荐的策略名称
        """
        # 获取模型推荐策略
        model_strategy = cls.MODEL_STRATEGY_MAP.get(model_name, "HYBRID")
        
        # 获取查询类型推荐策略
        query_strategy = cls.QUERY_STRATEGY_MAP.get(query_type, "HYBRID")
        
        # 如果消息数量超过阈值，优先使用滑动窗口或混合策略
        if message_count > max_messages:
            if model_strategy == "FULL_CONTEXT":
                return "HYBRID"  # 大窗口模型也使用混合策略
            return model_strategy
        
        # 根据查询类型和模型综合判断
        if query_strategy == "FULL_CONTEXT" and model_strategy in ["SLIDING_WINDOW", "HYBRID"]:
            return "HYBRID"
        
        return query_strategy
    
    @classmethod
    def detect_query_type(cls, user_query: str) -> str:
        """
        检测查询类型
        
        Args:
            user_query: 用户查询文本
            
        Returns:
            查询类型
        """
        query_lower = user_query.lower()
        
        # 检测八字相关关键词
        bazi_keywords = ["八字", "命理", "分析", "喜用神", "格局", "流年", "大运"]
        if any(kw in user_query for kw in bazi_keywords):
            if any(kw in query_lower for kw in ["请分析", "帮我分析", "我的八字"]):
                return "NEW_ANALYSIS"
            return "FOLLOW_UP"
        
        # 检测摘要相关关键词
        summary_keywords = ["总结", "概括", "简述", "要点"]
        if any(kw in user_query for kw in summary_keywords):
            return "SUMMARY_REQUEST"
        
        return "GENERAL_CHAT"
    
    @classmethod
    def get_strategy_description(cls, strategy: str) -> str:
        """
        获取策略描述
        
        Args:
            strategy: 策略名称
            
        Returns:
            策略描述
        """
        descriptions = {
            "FULL_CONTEXT": "全量上下文模式 - 使用所有历史对话作为上下文",
            "SLIDING_WINDOW": "滑动窗口模式 - 仅使用最近对话作为上下文",
            "HYBRID": "混合模式 - 使用关键消息 + 最近消息作为上下文",
        }
        return descriptions.get(strategy, "未知策略")
