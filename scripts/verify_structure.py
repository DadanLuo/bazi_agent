#!/usr/bin/env python3
"""
项目结构验证脚本
"""
from pathlib import Path

REQUIRED_FILES = [
    "requirements.txt",
    "pyproject.toml",
    ".env",
    "config/settings.py",
    "config/graph_config.yaml",
    "config/prompts.py",
    "src/__init__.py",
    "src/core/__init__.py",
    "src/graph/__init__.py",
    "src/rag/__init__.py",
]

REQUIRED_DIRS = [
    "config",
    "prompts",
    "src/core/engine",
    "src/core/models",
    "src/graph",
    "src/skills",
    "src/rag",
    "knowledge_base/raw_documents",
    "evaluation/test_cases",
    "tests",
    "scripts",
    "logs",
]


def verify_structure():
    """验证项目结构"""
    print("🔍 验证项目结构...\n")

    errors = []

    print("📄 检查必要文件:")
    for file_path in REQUIRED_FILES:
        if Path(file_path).exists():
            print(f"  ✅ {file_path}")
        else:
            print(f"  ❌ {file_path} (缺失)")
            errors.append(file_path)

    print("\n📁 检查必要目录:")
    for dir_path in REQUIRED_DIRS:
        if Path(dir_path).is_dir():
            print(f"  ✅ {dir_path}/")
        else:
            print(f"  ❌ {dir_path}/ (缺失)")
            errors.append(dir_path)

    print("\n" + "=" * 50)
    if errors:
        print(f"⚠️  发现 {len(errors)} 个问题，请检查上述缺失项")
        return False
    else:
        print("✅ 项目结构验证通过！")
        return True


if __name__ == "__main__":
    success = verify_structure()
    exit(0 if success else 1)