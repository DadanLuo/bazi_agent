# src/rag/knowledge_processor.py
import os
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import logging
import numpy as np
import dashscope
from dashscope import TextEmbedding
import chromadb

# 导入自定义模块
from src.config.rag_config import rag_config
from src.rag.term_normalizer import normalize
from src.rag.splitter.metadata_handler import process_document_with_metadata

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 路径配置
project_root = Path(__file__).parent.parent.parent
KNOWLEDGE_DIR = project_root / "knowledge_base/raw"
PROCESSED_DIR = project_root / "knowledge_base/processed"
DOCX_CACHE_DIR = PROCESSED_DIR / "converted_docx"
DOC_CONVERSION_TIMEOUT_SECONDS = 120
EXCLUDED_FILENAMES = {"treelist.txt"}
EXCLUDED_STEMS = {"treelist"}

# 确保目录存在
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
DOCX_CACHE_DIR.mkdir(parents=True, exist_ok=True)
Path(rag_config.chroma_persist_dir).mkdir(parents=True, exist_ok=True)

# API Key 配置
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY")
if not DASHSCOPE_API_KEY:
    raise EnvironmentError("未设置环境变量 DASHSCOPE_API_KEY")
dashscope.api_key = DASHSCOPE_API_KEY
CHROMA_PERSIST_DIR = rag_config.chroma_persist_dir
MD5_RECORD_FILE = rag_config.md5_record_file


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


def read_docx_text(file_path: Path) -> str:
    """读取 .docx 文件内容。"""
    try:
        from docx import Document

        doc = Document(file_path)
        return "\n".join([para.text for para in doc.paragraphs])
    except Exception as e:
        logger.error(f"读取 .docx 失败: {file_path.name} - {e}")
        return ""


def get_cached_docx_path(file_path: Path, file_md5: str) -> Path:
    """为 .doc 文件生成稳定的缓存 .docx 路径。"""
    try:
        relative_path = file_path.relative_to(KNOWLEDGE_DIR)
    except ValueError:
        relative_path = Path(file_path.name)

    target_dir = DOCX_CACHE_DIR / relative_path.parent
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / f"{file_path.stem}__{file_md5[:12]}.docx"


class WordDocConverter:
    """使用 Word COM 将旧 .doc 转换为缓存 .docx。"""

    WD_FORMAT_XML_DOCUMENT = 16

    def __init__(self, timeout_seconds: int = DOC_CONVERSION_TIMEOUT_SECONDS):
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _conversion_script() -> str:
        return (
            "from pathlib import Path\n"
            "import sys\n"
            "import win32com.client\n"
            "source = Path(sys.argv[1])\n"
            "target = Path(sys.argv[2])\n"
            "target.parent.mkdir(parents=True, exist_ok=True)\n"
            "word = win32com.client.DispatchEx('Word.Application')\n"
            "word.Visible = False\n"
            "word.DisplayAlerts = 0\n"
            "doc = None\n"
            "try:\n"
            "    doc = word.Documents.Open(\n"
            "        str(source.resolve()),\n"
            "        ConfirmConversions=False,\n"
            "        ReadOnly=True,\n"
            "        AddToRecentFiles=False,\n"
            "        NoEncodingDialog=True,\n"
            "    )\n"
            f"    doc.SaveAs2(str(target.resolve()), FileFormat={WordDocConverter.WD_FORMAT_XML_DOCUMENT})\n"
            "finally:\n"
            "    if doc is not None:\n"
            "        doc.Close(False)\n"
            "    word.Quit()\n"
        )

    def convert(self, source_path: Path, target_path: Path) -> Path:
        """将 .doc 转换为 .docx；如果缓存已存在则直接复用。"""
        if target_path.exists():
            logger.info(f"复用缓存 .docx: {target_path.name}")
            return target_path

        try:
            logger.info(f"转换 .doc -> .docx: {source_path.name}")
            subprocess.run(
                [
                    sys.executable,
                    "-c",
                    self._conversion_script(),
                    str(source_path.resolve()),
                    str(target_path.resolve()),
                ],
                check=True,
                timeout=self.timeout_seconds,
                capture_output=True,
                text=True,
            )
            return target_path
        except subprocess.TimeoutExpired as e:
            if target_path.exists():
                target_path.unlink()
            logger.error(f".doc 转换超时: {source_path.name} ({self.timeout_seconds}s)")
            raise RuntimeError(
                f".doc 转换超时: {source_path.name} ({self.timeout_seconds}s)"
            ) from e
        except subprocess.CalledProcessError as e:
            if target_path.exists():
                target_path.unlink()
            stderr = (e.stderr or "").strip()
            stdout = (e.stdout or "").strip()
            detail = stderr or stdout or str(e)
            raise RuntimeError(f".doc 转换失败: {source_path.name} - {detail}") from e

    def close(self):
        """兼容旧调用；子进程模式下无需显式关闭。"""
        return None


def load_document(
    file_path: Path,
    *,
    file_md5: Optional[str] = None,
    converter: Optional[WordDocConverter] = None,
) -> str:
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
            except Exception as e:
                logger.error(f"读取 .txt 失败: {file_path.name} - {e}")
                return ""
        return ""

    elif suffix == ".docx":
        return read_docx_text(file_path)

    elif suffix == ".doc":
        local_converter = converter or WordDocConverter()
        try:
            doc_md5 = file_md5 or compute_file_md5(file_path)
            cached_docx = get_cached_docx_path(file_path, doc_md5)
            converted_path = local_converter.convert(file_path, cached_docx)
            return read_docx_text(converted_path)
        except Exception as e:
            logger.error(f"读取 .doc 失败: {file_path.name} - {e}")
            return ""
        finally:
            if converter is None:
                local_converter.close()

    return ""


def clean_text(text: str) -> str:
    """清洗文本"""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\u4e00-\u9fa5a-zA-Z0-9，。；：？！“”‘’（）【】《》\s]", "", text)
    return text.strip()


def should_index_file(file_path: Path) -> bool:
    """过滤明显不是知识正文的文件。"""
    if file_path.name.lower() in EXCLUDED_FILENAMES:
        return False
    if file_path.stem.lower() in EXCLUDED_STEMS:
        return False
    return True


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
            response = TextEmbedding.call(model=rag_config.embedding_model, input=batch)
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
) -> Tuple[List[str], List[List[float]], List[int]]:
    """使用 NumPy 加速的去重算法，返回去重后的数据和保留的索引"""
    if not embeddings:
        return [], [], []

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

    return [chunks[i] for i in unique_indices], [embeddings[i] for i in unique_indices], unique_indices


# ============== ChromaDB 相关 ==============

def init_chromadb(reset_current: bool = False) -> chromadb.Collection:
    """初始化 ChromaDB 集合"""
    client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    if reset_current:
        try:
            client.delete_collection(name=rag_config.collection_name)
            logger.info(f"🗑️ 已删除当前版本集合: {rag_config.collection_name}")
        except Exception:
            logger.info(f"当前版本集合不存在，无需删除: {rag_config.collection_name}")
    collection = client.get_or_create_collection(
        name=rag_config.collection_name,
        metadata=rag_config.collection_metadata,
    )
    return collection


def add_to_chromadb_batch(
        collection: chromadb.Collection,
        chunks: List[str],
        embeddings: List[List[float]],
        metadatas: List[Dict],
        batch_size: int = 5000
):
    """分批添加数据到 ChromaDB"""
    total = len(chunks)
    total_batches = (total + batch_size - 1) // batch_size

    def sanitize_metadata(metadata: Dict) -> Dict:
        """清洗 metadata，避免 ChromaDB 拒绝空列表或空值。"""
        sanitized = {}

        for key, value in metadata.items():
            if value is None:
                continue
            if isinstance(value, str):
                stripped = value.strip()
                if stripped:
                    sanitized[key] = stripped
                continue
            if isinstance(value, list):
                cleaned_list = []
                for item in value:
                    if item is None:
                        continue
                    if isinstance(item, str):
                        item = item.strip()
                        if not item:
                            continue
                    cleaned_list.append(item)
                if cleaned_list:
                    sanitized[key] = cleaned_list
                continue
            sanitized[key] = value

        return sanitized

    for i in range(0, total, batch_size):
        end_idx = min(i + batch_size, total)
        batch_num = i // batch_size + 1

        logger.info(f"⚡ 写入 ChromaDB: [{batch_num}/{total_batches}] ({i + 1}-{end_idx}/{total})")

        # 准备数据
        ids = [f"chunk_{j}" for j in range(i, end_idx)]
        documents = chunks[i:end_idx]
        batch_embeddings = embeddings[i:end_idx]
        batch_metadatas = [sanitize_metadata(m) for m in metadatas[i:end_idx]]

        # 添加到集合
        try:
            collection.add(
                ids=ids,
                documents=documents,
                embeddings=batch_embeddings,
                metadatas=batch_metadatas
            )
        except Exception as e:
            logger.error(f"批次 {batch_num} 写入失败: {e}")
            raise

    logger.info(f"✅ ChromaDB 写入完成，共 {total} 条记录")


# ============== 主处理流程 ==============

def process_documents(force_rebuild_current: bool = False):
    """主处理流程：文档 → 切片 → Embedding → 去重 → ChromaDB"""

    print("=" * 60)
    print("开始构建命理知识库")
    print("=" * 60)
    print(f"目标集合: {rag_config.collection_name}")
    print(f"Embedding 模型: {rag_config.embedding_model}")
    print(f"切分器版本: {rag_config.splitter_name}/{rag_config.splitter_version}")
    print(f"增量记录文件: {MD5_RECORD_FILE}")

    if force_rebuild_current:
        logger.warning(f"⚠️ 强制重建当前版本集合: {rag_config.collection_name}")
        if MD5_RECORD_FILE.exists():
            MD5_RECORD_FILE.unlink()
            logger.info(f"🗑️ 已删除增量记录文件: {MD5_RECORD_FILE.name}")
        init_chromadb(reset_current=True)

    # === 步骤 1：扫描文件 ===
    print(f"\n扫描目录: {KNOWLEDGE_DIR.resolve()}")
    all_items = list(KNOWLEDGE_DIR.rglob("*"))

    # 统计文件类型
    file_stats = {}
    for item in all_items:
        if item.is_file():
            ext = item.suffix.lower()
            file_stats[ext] = file_stats.get(ext, 0) + 1
    print(f"文件类型统计: {file_stats}")

    supported_files = [
        f for f in all_items
        if f.suffix.lower() in (".txt", ".docx", ".doc")
        and f.is_file()
        and should_index_file(f)
    ]
    print(f"符合条件的文件: {len(supported_files)} 个\n")

    if not supported_files:
        logger.warning("未找到支持的文件")
        return

    # === 步骤 2：MD5 去重 ===
    processed_md5 = load_processed_md5()
    existing_collection = init_chromadb()
    existing_count = existing_collection.count()

    if processed_md5 and existing_count == 0:
        logger.warning(
            "当前版本集合为空，但检测到旧的增量记录；将忽略该记录并执行全量重建"
        )
        processed_md5 = {}

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
    all_metadatas = []
    file_md5_updates = {}
    doc_converter = WordDocConverter()

    try:
        for file_path, md5, rel_path in new_files:
            logger.info(f"📄 处理: {rel_path}")
            content = load_document(file_path, file_md5=md5, converter=doc_converter)
            if content:
                # 标准化内容
                normalized_content = normalize(content)
                cleaned_content = clean_text(normalized_content)
                
                # 使用递归切分器处理文档，保留完整的元数据信息
                processed_chunks = process_document_with_metadata(
                    cleaned_content, 
                    source=file_path.stem
                )
                
                # 提取chunks和metadata
                for chunk_data in processed_chunks:
                    chunk_content = chunk_data["content"]
                    chunk_metadata = chunk_data["metadata"]
                    all_chunks.append(chunk_content)
                    all_metadatas.append(chunk_metadata)
                file_md5_updates[rel_path] = md5
    finally:
        doc_converter.close()

    logger.info(f"✅ 生成文本块: {len(all_chunks)} 个\n")

    # === 步骤 4：生成 Embedding ===
    if all_chunks:
        logger.info("🔄 调用 Embedding API...")
        embeddings = get_qwen_embeddings(all_chunks)
        logger.info(f"✅ 向量生成完成\n")
    else:
        logger.warning("没有新文本块需要处理")
        embeddings = []
        all_metadatas = []

    # === 步骤 5：相似度去重 ===
    if all_chunks and embeddings:
        logger.info("🔍 执行相似度去重...")
        unique_chunks, unique_embeddings, unique_indices = deduplicate_by_similarity_fast(
            all_chunks, embeddings, threshold=0.9
        )
        
        # 同步去重 metadata
        unique_metadatas = [all_metadatas[i] for i in unique_indices]
        logger.info("")
    else:
        unique_chunks, unique_embeddings, unique_metadatas = [], [], []

    # === 步骤 6：写入 ChromaDB ===
    if unique_chunks and unique_embeddings:
        logger.info("💾 初始化 ChromaDB...")
        collection = init_chromadb()

        # 检查是否已有数据
        existing_count = collection.count()
        if existing_count > 0:
            logger.warning(
                f"⚠️ 当前集合 {rag_config.collection_name} 中已有 {existing_count} 条记录"
            )
            # 可选：清空重建，或者追加
            # 这里选择追加模式（如果 MD5 记录正确，应该不会有重复）

        logger.info("📦 写入向量数据库...")
        add_to_chromadb_batch(collection, unique_chunks, unique_embeddings, unique_metadatas)
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
    print("构建完成统计")
    print("=" * 60)

    collection = init_chromadb()
    final_count = collection.count()

    print(f"处理文件数: {len(new_files)}")
    print(f"原始文本块: {len(all_chunks)}")
    print(f"去重后数量: {len(unique_chunks)}")
    print(f"数据库总记录: {final_count}")
    print(f"持久化路径: {CHROMA_PERSIST_DIR}")
    print(f"当前集合: {rag_config.collection_name}")
    print("=" * 60)


if __name__ == "__main__":
    process_documents()
