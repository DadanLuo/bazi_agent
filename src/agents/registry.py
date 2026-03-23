# src/agents/registry.py
"""
Agent 注册表 — 注册、查找、路由 Agent
"""
from typing import Dict, Optional
import logging

from src.agents.base import BaseAgent
from src.core.contracts import UnifiedSession

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Agent 注册表"""
    _agents: Dict[str, BaseAgent] = {}

    @classmethod
    def register(cls, agent: BaseAgent) -> None:
        cls._agents[agent.agent_id] = agent
        logger.info(f"注册 Agent: {agent.agent_id} ({agent.display_name})")

    @classmethod
    def get(cls, agent_id: str) -> Optional[BaseAgent]:
        return cls._agents.get(agent_id)

    @classmethod
    def get_or_default(cls, agent_id: str, default_id: str = "bazi") -> BaseAgent:
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

        优先使用 session 中已绑定的 agent_id，保持对话一致性。
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
        """返回 {agent_id: display_name}"""
        return {aid: a.display_name for aid, a in cls._agents.items()}
