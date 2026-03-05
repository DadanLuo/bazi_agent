#!/usr/bin/env python3
"""
知识库初始化脚本
"""
import os
from pathlib import Path


def setup_knowledge_base():
    """初始化知识库目录结构"""
    base_dirs = [
        "knowledge_base/raw_documents/guji",
        "knowledge_base/raw_documents/geju",
        "knowledge_base/raw_documents/wangshuai",
        "knowledge_base/raw_documents/mangpai",
        "knowledge_base/raw_documents/rules",
        "knowledge_base/processed",
        "knowledge_base/vector_store",
    ]

    for dir_path in base_dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        gitkeep = Path(dir_path) / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()

    # 创建敏感词库文件
    sensitive_keywords = [
        "自杀", "死亡", "灾难", "血光", "官司",
        "赌博", "投资", "医疗", "怀孕", "堕胎",
        "彩票", "股票", "基金", "贷款", "保险"
    ]

    with open("config/sensitive_keywords.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(sensitive_keywords))

    print("✅ 知识库目录初始化完成！")
    print(f"📁 知识库根目录：{Path('knowledge_base').absolute()}")


if __name__ == "__main__":
    setup_knowledge_base()