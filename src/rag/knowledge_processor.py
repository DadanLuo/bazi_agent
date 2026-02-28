# src/rag/knowledge_processor.py
import os
import hashlib
import json
import re
import math
from pathlib import Path
from typing import List, Dict, Tuple
import logging
import numpy as np
import dashscope
from dashscope import TextEmbedding
import chromadb
from chromadb.config import Settings

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 路径配置
project_root = Path(__file__).parent.parent.parent
KNOWLEDGE_DIR = project_root / "knowledge_base/raw"
PROCESSED_DIR = project_root / "knowledge_base/processed"
MD5_RECORD_FILE = PROCESSED_DIR / "processed_files_md5.json"
CHROMA_PERSIST_DIR = str(project_root / "chroma_db")

# 确保目录存在
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# API Key 配置
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
if not DASHSCOPE_API_KEY:
    raise EnvironmentError("未设置环境变量 DASHSCOPE_API_KEY")
dashscope.api_key = DASHSCOPE_API_KEY


# ============== 基础工具函数 ==============

def compute_file_md5(file_path: Path) -> str:
    """计算文件 MD5"""
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def load_processed_md5() -> Dict[str, str]:
    """加载 MD5 记录"""
    if MD5_RECORD_FILE.exists():
        with open(MD5_RECORD_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_processed_md5(md5_dict: Dict[str, str]):
    """保存 MD5 记录"""
    with open(MD5_RECORD_FILE, "w", encoding="utf-8") as f:
        json.dump(md5_dict, f, ensure_ascii=False, indent=2)


def load_document(file_path: Path) -> str:
    """加载文档内容（支持 .txt, .docx, .doc）"""
    suffix = file_path.suffix.lower()

    if suffix == ".txt":
        encodings = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'utf-16']
        for enc in encodings:
            try:
                with open(file_path, "r", encoding=enc) as f:
                    return f.read()
            except UnicodeDecodeError:
                continue
        return ""

    elif suffix == ".docx":
        try:
            from docx import Document
            doc = Document(file_path)
            return "\n".join([para.text for para in doc.paragraphs])
        except Exception as e:
            logger.error(f"读取 .docx 失败: {file_path.name} - {e}")
            return ""

    elif suffix == ".doc":
        try:
            import win32com.client
            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            doc = word.Documents.Open(str(file_path.resolve()))
            text = doc.Content.Text
            doc.Close(False)
            word.Quit()
            return text
        except Exception as e:
            logger.error(f"读取 .doc 失败: {file_path.name} - {e}")
            return ""

    return ""


def clean_text(text: str) -> str:
    """清洗文本"""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9，。；：？！“”‘’（）【】《》\s]", "", text)
    return text.strip()


def smart_chunk_text(text: str, max_length: int = 512, overlap: int = 50) -> List[str]:
    """智能分块"""
    if len(text) <= max_length:
        return [text.strip()] if text.strip() else []

    chunks = []
    start = 0
    while start < len(text):
        end = start + max_length
        chunks.append(text[start:end])
        start = end - overlap

    return [c.strip() for c in chunks if c.strip()]


# ============== Embedding 相关 ==============

def get_qwen_embeddings(texts: List[str], batch_size: int = 10) -> List[List[float]]:
    """调用 Embedding API（自动分批）"""
    if not texts:
        return []

    all_embeddings = []
    total_batches = (len(texts) + batch_size - 1) // batch_size

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        batch_num = i // batch_size + 1

        try:
            response = TextEmbedding.call(model="text-embedding-v4", input=batch)
            if response.status_code != 200:
                raise RuntimeError(f"API 错误: {response.code}")

            batch_embeddings = [item["embedding"] for item in response.output["embeddings"]]
            all_embeddings.extend(batch_embeddings)

            logger.info(
                f"✅ Embedding 进度: [{batch_num}/{total_batches}] ({i + 1}-{min(i + batch_size, len(texts))}/{len(texts)})")
        except Exception as e:
            logger.error(f"批次 {batch_num} 失败: {e}")
            raise

    return all_embeddings


# ============== 相似度去重（NumPy 加速）==============

def deduplicate_by_similarity_fast(
        chunks: List[str],
        embeddings: List[List[float]],
        threshold: float = 0.9
) -> Tuple[List[str], List[List[float]]]:
    """使用 NumPy 加速的去重算法"""
    if not embeddings:
        return [], []

    logger.info("🔄 正在计算相似度矩阵（加速模式）...")

    # 转换为 NumPy 数组
    emb_matrix = np.array(embeddings, dtype=np.float32)

    # 归一化
    norms = np.linalg.norm(emb_matrix, axis=1, keepdims=True)
    emb_normalized = emb_matrix / norms

    # 逐个检查是否重复
    unique_indices = [0]  # 第一个肯定保留

    for i in range(1, len(chunks)):
        # 只与已保留的块比较
        kept_embeddings = emb_normalized[unique_indices]
        current_emb = emb_normalized[i:i + 1]

        # 计算相似度
        similarities = np.dot(kept_embeddings, current_emb.T)

        if np.max(similarities) <= threshold:
            unique_indices.append(i)

        # 进度显示
        if (i + 1) % 1000 == 0:
            logger.info(f"   去重进度: {i + 1}/{len(chunks)}, 已保留 {len(unique_indices)} 个")

    logger.info(f"✅ 去重完成: {len(chunks)} → {len(unique_indices)} 个")

    return [chunks[i] for i in unique_indices], [embeddings[i] for i in unique_indices]


# ============== ChromaDB 相关 ==============

def init_chromadb() -> chromadb.Collection:
    """初始化 ChromaDB 集合"""
    client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    collection = client.get_or_create_collection(
        name="bazi_knowledge",
        metadata={"hnsw:space": "cosine"}
    )
    return collection


def add_to_chromadb_batch(
        collection: chromadb.Collection,
        chunks: List[str],
        embeddings: List[List[float]],
        batch_size: int = 5000
):
    """分批添加数据到 ChromaDB"""
    total = len(chunks)
    total_batches = (total + batch_size - 1) // batch_size

    for i in range(0, total, batch_size):
        end_idx = min(i + batch_size, total)
        batch_num = i // batch_size + 1

        logger.info(f"⚡ 写入 ChromaDB: [{batch_num}/{total_batches}] ({i + 1}-{end_idx}/{total})")

        # 准备数据
        ids = [f"chunk_{j}" for j in range(i, end_idx)]
        documents = chunks[i:end_idx]
        batch_embeddings = embeddings[i:end_idx]
        metadatas = [{"source": "bazi_classics"} for _ in range(i, end_idx)]

        # 添加到集合
        try:
            collection.add(
                ids=ids,
                documents=documents,
                embeddings=batch_embeddings,
                metadatas=metadatas
            )
        except Exception as e:
            logger.error(f"批次 {batch_num} 写入失败: {e}")
            raise

    logger.info(f"✅ ChromaDB 写入完成，共 {total} 条记录")


# ============== 主处理流程 ==============

def process_documents():
    """主处理流程：文档 → 切片 → Embedding → 去重 → ChromaDB"""

    print("=" * 60)
    print("🚀 开始构建命理知识库")
    print("=" * 60)

    # === 步骤 1：扫描文件 ===
    print(f"\n🔍 扫描目录: {KNOWLEDGE_DIR.resolve()}")
    all_items = list(KNOWLEDGE_DIR.rglob("*"))

    # 统计文件类型
    file_stats = {}
    for item in all_items:
        if item.is_file():
            ext = item.suffix.lower()
            file_stats[ext] = file_stats.get(ext, 0) + 1
    print(f"📂 文件类型统计: {file_stats}")

    supported_files = [f for f in all_items if f.suffix.lower() in (".txt", ".docx", ".doc") and f.is_file()]
    print(f"✅ 符合条件的文件: {len(supported_files)} 个\n")

    if not supported_files:
        logger.warning("未找到支持的文件")
        return

    # === 步骤 2：MD5 去重 ===
    processed_md5 = load_processed_md5()

    # 如果实际文件数多于记录数，重置
    if len(processed_md5) > 0 and len(supported_files) > len(processed_md5):
        logger.warning(f"检测到新文件 (记录:{len(processed_md5)} vs 实际:{len(supported_files)})，重置处理记录")
        processed_md5 = {}

    new_files = []
    for file_path in supported_files:
        md5 = compute_file_md5(file_path)
        rel_path = str(file_path.relative_to(KNOWLEDGE_DIR))
        if rel_path in processed_md5 and processed_md5[rel_path] == md5:
            continue
        new_files.append((file_path, md5, rel_path))

    if not new_files:
        logger.info("✅ 没有新文件需要处理\n")
    else:
        logger.info(f"🆕 发现 {len(new_files)} 个新文件\n")

    # === 步骤 3：处理文档（切片）===
    all_chunks = []
    file_md5_updates = {}

    for file_path, md5, rel_path in new_files:
        logger.info(f"📄 处理: {rel_path}")
        content = load_document(file_path)
        if content:
            chunks = smart_chunk_text(clean_text(content))
            all_chunks.extend(chunks)
            file_md5_updates[rel_path] = md5

    logger.info(f"✅ 生成文本块: {len(all_chunks)} 个\n")

    # === 步骤 4：生成 Embedding ===
    if all_chunks:
        logger.info("🔄 调用 Embedding API...")
        embeddings = get_qwen_embeddings(all_chunks)
        logger.info(f"✅ 向量生成完成\n")
    else:
        logger.warning("没有新文本块需要处理")
        embeddings = []

    # === 步骤 5：相似度去重 ===
    if all_chunks and embeddings:
        logger.info("🔍 执行相似度去重...")
        unique_chunks, unique_embeddings = deduplicate_by_similarity_fast(
            all_chunks, embeddings, threshold=0.9
        )
        logger.info("")
    else:
        unique_chunks, unique_embeddings = [], []

    # === 步骤 6：写入 ChromaDB ===
    if unique_chunks and unique_embeddings:
        logger.info("💾 初始化 ChromaDB...")
        collection = init_chromadb()

        # 检查是否已有数据
        existing_count = collection.count()
        if existing_count > 0:
            logger.warning(f"⚠️ ChromaDB 中已有 {existing_count} 条记录")
            # 可选：清空重建，或者追加
            # 这里选择追加模式（如果 MD5 记录正确，应该不会有重复）

        logger.info("📦 写入向量数据库...")
        add_to_chromadb_batch(collection, unique_chunks, unique_embeddings)
        logger.info("")
    else:
        logger.info("⚠️ 没有数据需要写入 ChromaDB\n")

    # === 步骤 7：更新 MD5 记录 ===
    if file_md5_updates:
        processed_md5.update(file_md5_updates)
        save_processed_md5(processed_md5)
        logger.info(f"📝 更新 MD5 记录: {len(processed_md5)} 个文件\n")

    # === 步骤 8：验证结果 ===
    print("=" * 60)
    print("📊 构建完成统计")
    print("=" * 60)

    collection = init_chromadb()
    final_count = collection.count()

    print(f"✅ 处理文件数: {len(new_files)}")
    print(f"✅ 原始文本块: {len(all_chunks)}")
    print(f"✅ 去重后数量: {len(unique_chunks)}")
    print(f"✅ 数据库总记录: {final_count}")
    print(f"✅ 持久化路径: {CHROMA_PERSIST_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    process_documents()
