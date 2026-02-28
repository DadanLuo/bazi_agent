# src/rag/build_knowledge_base.py
from src.rag.knowledge_processor import process_documents
import os
from pathlib import Path


def build_knowledge_base():
    """构建知识库主入口"""
    # 切换到项目根目录
    project_root = Path(__file__).parent.parent.parent
    os.chdir(project_root)

    # 执行处理流程（现在包含 ChromaDB 写入）
    process_documents()


if __name__ == "__main__":
    build_knowledge_base()
