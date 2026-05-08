"""
Prompt 模板管理器
支持版本控制、动态加载、变量替换
"""
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime


class PromptManager:
    """Prompt 模板管理器"""

    def __init__(self, prompts_dir: Path = None):
        self.prompts_dir = prompts_dir or Path(__file__).parent.parent / "prompts"
        self.versions_dir = self.prompts_dir / "versions"
        self._cache: Dict[str, Dict] = {}

    def load_prompt(self, name: str, version: str = "current") -> Dict[str, Any]:
        """加载指定 Prompt 模板"""
        cache_key = f"{name}:{version}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        if version == "current":
            prompt_path = self.versions_dir / "current" / f"{name}.yaml"
        else:
            prompt_path = self.versions_dir / version / f"{name}.yaml"

        if not prompt_path.exists():
            prompt_path = self.prompts_dir / "task_prompts" / f"{name}.yaml"

        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt not found: {prompt_path}")

        with open(prompt_path, "r", encoding="utf-8") as f:
            prompt_data = yaml.safe_load(f)

        self._cache[cache_key] = prompt_data
        return prompt_data

    def render(self, name: str, variables: Dict[str, Any], version: str = "current") -> str:
        """渲染 Prompt 模板"""
        prompt_data = self.load_prompt(name, version)
        template = prompt_data.get("template", "")

        rendered = template
        for key, value in variables.items():
            rendered = rendered.replace(f"{{{key}}}", str(value))

        return rendered

    def list_versions(self, name: str) -> list:
        """列出 Prompt 的所有版本"""
        if not self.versions_dir.exists():
            return []

        versions = []
        for version_dir in self.versions_dir.iterdir():
            if version_dir.is_dir():
                prompt_file = version_dir / f"{name}.yaml"
                if prompt_file.exists():
                    versions.append(version_dir.name)

        return sorted(versions)


# 单例实例
prompt_manager = PromptManager()