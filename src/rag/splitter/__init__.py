"""
RAG Splitter 模块
"""
from .recursive_splitter import RecursiveTextSplitter, recursive_splitter, split_document_recursive
from .metadata_handler import MetadataHandler, metadata_handler, process_document_with_metadata