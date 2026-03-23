# src/agents/__init__.py
"""Agent 抽象层"""
from src.agents.base import BaseAgent, SlotSchema
from src.agents.registry import AgentRegistry

__all__ = ["BaseAgent", "SlotSchema", "AgentRegistry"]
