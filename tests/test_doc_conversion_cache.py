from pathlib import Path

from src.rag.knowledge_processor import DOCX_CACHE_DIR, get_cached_docx_path


def test_cached_docx_path_is_scoped_by_md5():
    source = Path("D:/bazi-agent/knowledge_base/raw/folder/sample.doc")

    path_a = get_cached_docx_path(source, "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
    path_b = get_cached_docx_path(source, "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb")

    assert path_a != path_b
    assert path_a.parent == DOCX_CACHE_DIR / "folder"
    assert path_b.parent == DOCX_CACHE_DIR / "folder"
    assert path_a.suffix == ".docx"
    assert "__aaaaaaaaaaaa.docx" in path_a.name
