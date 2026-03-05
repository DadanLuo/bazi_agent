# src/graph/__init__.py
"""图工作流模块"""
from .state import (
    BaziAgentState,
    ContextStrategy,
    RetrievalMode,
    IntentType,
    create_initial_state,
    update_state_with_message,
    get_current_messages,
    get_last_user_message,
    get_last_assistant_message
)
from .bazi_graph import create_bazi_graph
from .chat_nodes import (
    chat_node,
    intent_router_node,
    chat_generate_node,
    chat_save_node,
    chat_safety_check_node
)

__all__ = [
    "BaziAgentState",
    "ContextStrategy",
    "RetrievalMode",
    "IntentType",
    "create_initial_state",
    "update_state_with_message",
    "get_current_messages",
    "get_last_user_message",
    "get_last_assistant_message",
    "create_bazi_graph",
    "chat_node",
    "intent_router_node",
    "chat_generate_node",
    "chat_save_node",
    "chat_safety_check_node"
]
