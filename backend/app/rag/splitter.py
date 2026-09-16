"""文本切分（LangChain Text Splitter）。"""

from __future__ import annotations

from typing import Any

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 分隔符优先级：段落 → 换行 → 中文句末 → 英文句末 → 空格 → 单字
_SEPARATORS = ["\n\n", "\n", "。", "！", "？", "；", "，", ". ", "! ", "? ", "; ", " ", ""]


def build_splitter(chunk_size: int, chunk_overlap: int) -> RecursiveCharacterTextSplitter:
    """构建递归字符切分器（针对中英文混合文本优化）。"""
    chunk_size = max(100, int(chunk_size))
    chunk_overlap = min(max(0, int(chunk_overlap)), chunk_size - 1)
    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=_SEPARATORS,
        length_function=len,
        keep_separator=True,
        add_start_index=True,
    )


def split_documents(
    documents: list[Document],
    chunk_size: int,
    chunk_overlap: int,
    *,
    extra_metadata: dict[str, Any] | None = None,
) -> list[Document]:
    """切分文档并追加统一 metadata（chunk_index 从 0 递增）。"""
    splitter = build_splitter(chunk_size, chunk_overlap)
    chunks = splitter.split_documents(documents)
    result: list[Document] = []
    for index, chunk in enumerate(chunks):
        content = chunk.page_content.strip()
        if not content:
            continue
        metadata: dict[str, Any] = {
            **(extra_metadata or {}),
            **{k: v for k, v in chunk.metadata.items() if v is not None},
            "chunk_index": index,
        }
        result.append(Document(page_content=content, metadata=metadata))
    return result


def estimate_tokens(text: str) -> int:
    """粗略 token 估算：中文 1 字 ≈ 1 token，英文 4 字符 ≈ 1 token。"""
    if not text:
        return 0
    chinese = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other = len(text) - chinese
    return int(chinese + other / 4) or 1
