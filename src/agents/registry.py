# src/agents/registry.py
"""
Agent 注册表 — 注册、查找、路由 Agent

本模块提供 Agent 的注册、查找和路由功能，支持多领域 Agent 的统一管理。

设计模式：
- 单例模式：全局唯一的 Agent 注册表
- 策略模式：根据用户查询自动选择合适的 Agent

使用方式：
    from src.agents.registry import AgentRegistry
    from src.agents.bazi_agent import BaziAgent
    
    # 注册 Agent
    AgentRegistry.register(BaziAgent())
    
    # 获取 Agent
    agent = AgentRegistry.get("bazi")
    
    # 自动路由
    agent = AgentRegistry.detect_agent("帮我算一下八字")
"""
from typing import Dict, Optional
import logging

from src.agents.base import BaseAgent
from src.core.contracts import UnifiedSession

logger = logging.getLogger(__name__)


class AgentRegistry:
    """
    Agent 注册表
    
    全局单例，管理所有已注册的 Agent 实例。
    支持按 ID 查找、自动路由和列表查询。
    
    Attributes:
        _agents: Agent 字典，key 为 agent_id，value 为 BaseAgent 实例
    """
    _agents: Dict[str, BaseAgent] = {}

    @classmethod
    def register(cls, agent: BaseAgent) -> None:
        """
        注册 Agent
        
        Args:
            agent: Agent 实例
        """
        cls._agents[agent.agent_id] = agent
        logger.info(f"注册 Agent: {agent.agent_id} ({agent.display_name})")

    @classmethod
    def get(cls, agent_id: str) -> Optional[BaseAgent]:
        """
        根据 ID 获取 Agent
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Optional[BaseAgent]: Agent 实例，不存在则返回 None
        """
        return cls._agents.get(agent_id)

    @classmethod
    def get_or_default(cls, agent_id: str, default_id: str = "bazi") -> BaseAgent:
        """
        获取 Agent，不存在则返回默认 Agent
        
        Args:
            agent_id: Agent ID
            default_id: 默认 Agent ID，默认为 "bazi"
            
        Returns:
            BaseAgent: Agent 实例
            
        Raises:
            KeyError: 当指定的 Agent 和默认 Agent 都不存在时抛出
        """
        agent = cls._agents.get(agent_id)
        if agent is None:
            agent = cls._agents.get(default_id)
        if agent is None:
            raise KeyError(f"Agent '{agent_id}' 和默认 Agent '{default_id}' 均未注册")
        return agent

    @classmethod
    def detect_agent(cls, query: str, session: Optional[UnifiedSession] = None) -> BaseAgent:
        """
        根据 session 的 agent_id 或 query 内容路由到合适的 Agent
        
        路由优先级：
        1. 优先使用 session 中已绑定的 agent_id（保持对话一致性）
        2. 关键词匹配（如 "塔罗"、"占卜" 等）
        3. 默认返回八字 Agent
        
        Args:
            query: 用户查询文本
            session: 会话对象，包含已绑定的 agent_id
            
        Returns:
            BaseAgent: 匹配的 Agent 实例
        """
        # 1. 优先用 session 绑定的 agent
        if session and session.metadata.agent_id:
            agent = cls._agents.get(session.metadata.agent_id)
            if agent:
                return agent

        # 2. 关键词路由
        tarot_keywords = ["塔罗", "占卜", "抽牌", "牌阵", "塔罗牌"]
        if any(kw in query for kw in tarot_keywords):
            agent = cls._agents.get("tarot")
            if agent:
                return agent

        # 3. 默认 bazi
        return cls.get_or_default("bazi")

    @classmethod
    def list_agents(cls) -> Dict[str, str]:
        """
        返回所有已注册的 Agent 列表
        
        Returns:
            Dict[str, str]: {agent_id: display_name} 映射
        """
        return {aid: a.display_name for aid, a in cls._agents.items()}
