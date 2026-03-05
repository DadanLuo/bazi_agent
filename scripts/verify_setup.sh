#!/bin/bash
# ============================================================================
# 文件路径：scripts/verify_setup.sh
# 功能：验证所有模块导入是否正常
# ============================================================================

echo "============================================================"
echo "🔍 验证赛博司命 RAG 模块设置"
echo "============================================================"

# 1. 测试日志模块
echo -e "\n📝 测试日志模块..."
python -c "from src.logging_config import setup_logging, get_logger; print('✅ 日志模块 OK')"

# 2. 测试查重模块
echo -e "\n📊 测试查重模块..."
python -c "from src.rag.deduplication import DeduplicationManager; print('✅ 查重模块 OK')"

# 3. 测试文档处理器
echo -e "\n📄 测试文档处理器..."
python -c "from src.rag.knowledge_processor import KnowledgeProcessor; print('✅ 文档处理器 OK')"

# 4. 测试向量存储
echo -e "\n🗄️  测试向量存储..."
python -c "from src.rag.vector_store import VectorStoreManager; print('✅ 向量存储 OK')"

# 5. 创建日志目录
echo -e "\n📁 创建日志目录..."
mkdir -p logs
echo "✅ 日志目录已创建"

echo -e "\n============================================================"
echo "✅ 所有模块验证完成！"
echo "============================================================"