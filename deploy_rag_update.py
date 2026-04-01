#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
RAG 知识库更新部署脚本

此脚本用于重新构建知识库以使用新的 metadata 功能
"""
import os
from pathlib import Path

from src.config.rag_config import rag_config

def deploy_rag_update():
    """部署 RAG 更新"""
    print("="*60)
    print("Starting RAG Improvement Deployment")
    print("="*60)
    print(f"Target collection: {rag_config.collection_name}")
    print(f"Embedding model: {rag_config.embedding_model}")
    print(f"Splitter version: {rag_config.splitter_name}/{rag_config.splitter_version}")
    
    # 1. 检查必要文件
    print("\nChecking required files...")
    required_files = [
        "src/rag/metadata_extractor.py",
        "src/rag/term_normalizer.py",
        "src/rag/knowledge_processor.py",
        "src/rag/retriever.py",
        "src/rag/agentic/nodes.py",
        "src/rag/agentic/planner.py"
    ]
    
    for file in required_files:
        if not Path(file).exists():
            print(f"Missing required file: {file}")
            return False
        print(f"Found file: {file}")
    
    # 2. 版本隔离提示
    print("\nUsing version-isolated collection...")
    print("Older collections will be kept untouched.")
    
    # 3. 重新构建知识库
    print("\nRebuilding knowledge base...")
    try:
        from src.rag.knowledge_processor import process_documents
        print("Starting document processing...")
        process_documents(force_rebuild_current=True)
        print("Knowledge base rebuild completed")
    except Exception as e:
        print(f"Knowledge base rebuild failed: {e}")
        return False
    
    # 4. 验证部署
    print("\nVerifying deployment...")
    try:
        from src.rag.retriever import KnowledgeRetriever
        retriever = KnowledgeRetriever()
        
        # 测试简单的检索
        test_results = retriever.search("甲木", top_k=1)
        print(f"Search test successful, returned {len(test_results)} results")
        print(f"Collection in use: {retriever.collection_name}")
        
        # 测试 where 条件构建
        where_cond = retriever.build_where_from_query("甲木七杀格")
        print(f"Where condition building test successful: {where_cond}")
        
    except Exception as e:
        print(f"Deployment verification failed: {e}")
        return False
    
    # 5. 完成部署
    print("\nRAG Improvement Deployment Complete!")
    print("New features:")
    print("   - Metadata pre-computation replacing BM25")
    print("   - Term normalization processing")
    print("   - Precise filtering with Where conditions")
    print("   - Structured entity retrieval")
    print("="*60)
    
    return True

if __name__ == "__main__":
    success = deploy_rag_update()
    if success:
        print("\nDeployment successful! System updated with latest RAG features.")
    else:
        print("\nDeployment failed! Please check error messages.")
        exit(1)
