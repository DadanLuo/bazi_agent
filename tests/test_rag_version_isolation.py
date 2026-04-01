from dataclasses import replace

from src.config.rag_config import RagVersionSettings, build_collection_name


def test_collection_name_changes_when_embedding_changes():
    collection_a = build_collection_name(
        collection_prefix="bazi_knowledge",
        index_version="v2",
        embedding_provider="dashscope",
        embedding_model="text-embedding-v4",
        splitter_name="recursive",
        splitter_version="v1",
    )
    collection_b = build_collection_name(
        collection_prefix="bazi_knowledge",
        index_version="v2",
        embedding_provider="dashscope",
        embedding_model="text-embedding-v5",
        splitter_name="recursive",
        splitter_version="v1",
    )

    assert collection_a != collection_b


def test_collection_name_changes_when_splitter_changes():
    collection_a = build_collection_name(
        collection_prefix="bazi_knowledge",
        index_version="v2",
        embedding_provider="dashscope",
        embedding_model="text-embedding-v4",
        splitter_name="recursive",
        splitter_version="v1",
    )
    collection_b = build_collection_name(
        collection_prefix="bazi_knowledge",
        index_version="v2",
        embedding_provider="dashscope",
        embedding_model="text-embedding-v4",
        splitter_name="recursive",
        splitter_version="v2",
    )

    assert collection_a != collection_b


def test_md5_record_file_is_scoped_by_active_collection():
    settings_a = RagVersionSettings(
        chroma_persist_dir="D:/tmp/chroma",
        collection_prefix="bazi_knowledge",
        index_version="v2",
        embedding_provider="dashscope",
        embedding_model="text-embedding-v4",
        splitter_name="recursive",
        splitter_version="v1",
    )
    settings_b = replace(settings_a, splitter_version="v2")

    assert settings_a.collection_name != settings_b.collection_name
    assert settings_a.md5_record_file != settings_b.md5_record_file
    assert settings_a.collection_name in settings_a.md5_record_file.name
    assert settings_b.collection_name in settings_b.md5_record_file.name
