"""配置模块导出。"""

from pathlib import Path

_root_config_dir = Path(__file__).resolve().parents[2] / "config"
if _root_config_dir.is_dir():
    __path__.append(str(_root_config_dir))

from config.settings import settings
from src.config.model_config import (
    ContextStrategySelector,
    MODEL_CONFIGS,
    ModelConfig,
    get_default_model_config,
)

__all__ = [
    "ContextStrategySelector",
    "MODEL_CONFIGS",
    "ModelConfig",
    "get_default_model_config",
    "settings",
]
