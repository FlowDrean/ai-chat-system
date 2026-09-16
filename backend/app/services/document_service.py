"""文档服务：上传校验、保存、删除、重新向量化。"""

from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path

import aiofiles
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    FileTooLargeError,
    FileTypeUnsupportedError,
    NotFoundError,
    StorageError,
)
from app.core.logging import get_logger
from app.models.document import Document, DocumentStatus
from app.rag.loader import compute_file_hash, detect_file_type
from app.rag.pipeline import ingest_document, sanitize_error
from app.repositories.knowledge_repo import (
    DocumentChunkRepository,
    DocumentRepository,
    KnowledgeBaseRepository,
)
from app.repositories.prompt_repo import UsageRepository
from app.schemas.knowledge import DocumentDetail, DocumentOut
from app.services.knowledge_service import to_document_out

logger = get_logger(__name__)

_UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')

# 后台任务引用，防止被 GC 回收
_background_tasks: set[asyncio.Task] = set()


def schedule_ingestion(document_id: int, *, overwrite: bool = True) -> None:
    """把向量化任务丢到后台执行（不阻塞 HTTP 响应）。"""
    task = asyncio.create_task(ingest_document(document_id, overwrite=overwrite))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def sanitize_filename(filename: str) -> str:
    """文件名安全处理：去掉路径、控制字符，限制长度。"""
    name = Path(filename or "document").name
    name = _UNSAFE_FILENAME.sub("_", name).strip().strip(".")
    if not name:
        name = "document"
    if len(name) > 180:
        stem, dot, suffix = name.rpartition(".")
        name = (stem[:150] + dot + suffix) if dot else name[:180]
    return name


class DocumentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.documents = DocumentRepository(session)
        self.chunks = DocumentChunkRepository(session)
        self.kbs = KnowledgeBaseRepository(session)
        self.usage = UsageRepository(session)

    # ------------------------------------------------------------------ #
    async def list_documents(
        self,
        kb_id: int,
        user_id: int | None,
        *,
        status: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[DocumentOut], int]:
        await self._require_kb(kb_id, user_id)
        items, total = await self.documents.list_by_kb(
            kb_id, status=status, keyword=keyword, offset=(page - 1) * page_size, limit=page_size
        )
        return [to_document_out(d) for d in items], total

    async def list_all_documents(
        self,
        user_id: int | None,
        *,
        status: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """管理后台「文档管理」：跨知识库列出文档。"""
        from sqlalchemy import func, select

        from app.models.knowledge import KnowledgeBase

        conditions = []
        if user_id is not None:
            conditions.append(KnowledgeBase.user_id == user_id)
        if status:
            conditions.append(Document.status == status)
        if keyword:
            conditions.append(Document.filename.like(f"%{keyword}%"))

        count_stmt = (
            select(func.count())
            .select_from(Document)
            .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
            .where(*conditions)
        )
        total = int((await self.session.execute(count_stmt)).scalar_one() or 0)

        rows = (
            await self.session.execute(
                select(Document, KnowledgeBase.name)
                .join(KnowledgeBase, KnowledgeBase.id == Document.knowledge_base_id)
                .where(*conditions)
                .order_by(Document.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        items: list[dict] = []
        for document, kb_name in rows:
            data = to_document_out(document).model_dump()
            data["knowledge_base_name"] = kb_name
            items.append(data)
        return items, total

    async def get_document(self, document_id: int, user_id: int | None) -> Document:
        document = await self.documents.get_owned(document_id, user_id)
        if document is None:
            raise NotFoundError("文档不存在")
        return document

    async def get_detail(self, document_id: int, user_id: int | None) -> DocumentDetail:
        document = await self.get_document(document_id, user_id)
        chunks = await self.chunks.list_by_document(document_id, limit=20)
        detail = DocumentDetail(
            **to_document_out(document).model_dump(),
            preview_chunks=[
                {
                    "id": chunk.id,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "token_count": chunk.token_count,
                    "metadata": chunk.meta,
                }
                for chunk in chunks
            ],
        )
        return detail

    # ------------------------------------------------------------------ #
    async def upload_document(self, kb_id: int, file: UploadFile, user_id: int) -> DocumentOut:
        kb = await self._require_kb(kb_id, user_id)
        filename = sanitize_filename(file.filename or "document")

        file_type = detect_file_type(filename)
        if Path(filename).suffix.lower() not in settings.allowed_extension_set:
            raise FileTypeUnsupportedError(
                f"不允许上传该类型文件，当前允许：{', '.join(sorted(settings.allowed_extension_set))}"
            )

        stored_name = f"{uuid.uuid4().hex}{Path(filename).suffix.lower()}"
        target = settings.upload_path / stored_name
        size = 0
        try:
            async with aiofiles.open(target, "wb") as fp:
                while True:
                    block = await file.read(1024 * 1024)
                    if not block:
                        break
                    size += len(block)
                    if size > settings.max_upload_size:
                        await fp.close()
                        target.unlink(missing_ok=True)
                        raise FileTooLargeError(f"文件大小不能超过 {settings.max_upload_size_mb} MB")
                    await fp.write(block)
        except FileTooLargeError:
            raise
        except Exception as exc:  # noqa: BLE001
            target.unlink(missing_ok=True)
            logger.exception("保存上传文件失败：%s", exc)
            raise StorageError("文件保存失败") from exc
        finally:
            await file.close()

        if size == 0:
            target.unlink(missing_ok=True)
            raise FileTypeUnsupportedError("上传的文件为空")

        file_hash = await asyncio.to_thread(compute_file_hash, target)
        duplicate = await self.documents.find_duplicate(kb_id, file_hash)
        if duplicate is not None:
            target.unlink(missing_ok=True)
            logger.info("检测到重复文档 %s -> 复用已有记录 id=%s", filename, duplicate.id)
            return to_document_out(duplicate)

        document = Document(
            knowledge_base_id=kb_id,
            user_id=user_id,
            filename=filename,
            file_path=str(target.resolve()),
            file_type=file_type,
            file_size=size,
            file_hash=file_hash,
            status=DocumentStatus.PENDING,
            progress=0,
            stage_message="等待处理",
        )
        self.session.add(document)
        await self.session.flush()
        await self.kbs.recalculate_counts(kb_id)
        await self.session.commit()

        logger.info("上传文档成功 id=%s file=%s size=%s kb=%s", document.id, filename, size, kb.id)
        schedule_ingestion(document.id)
        return to_document_out(document)

    # ------------------------------------------------------------------ #
    async def delete_document(self, document_id: int, user_id: int | None) -> None:
        document = await self.get_document(document_id, user_id)
        kb_id = document.knowledge_base_id
        file_path = Path(document.file_path)

        await self.chunks.delete_by_document(document_id)
        await self.documents.delete(document)
        await self.kbs.recalculate_counts(kb_id)
        await self.session.commit()

        try:
            if file_path.exists() and file_path.is_file():
                file_path.unlink()
        except OSError as exc:  # pragma: no cover
            logger.warning("删除物理文件失败 id=%s: %s", document_id, exc)
        logger.info("删除文档 id=%s", document_id)

    async def reindex_document(self, document_id: int, user_id: int | None) -> DocumentOut:
        document = await self.get_document(document_id, user_id)
        if document.status == DocumentStatus.PENDING:
            raise StorageError("文档正在处理中，请稍后再试")
        document.status = DocumentStatus.PENDING
        document.progress = 0
        document.stage_message = "等待重新向量化"
        document.error_message = None
        await self.session.commit()

        schedule_ingestion(document.id, overwrite=True)
        logger.info("重新向量化文档 id=%s", document_id)
        return to_document_out(document)

    async def cancel_document(self, document_id: int, user_id: int | None) -> DocumentOut:
        """把失败 / 卡住的文档标记为失败。"""
        document = await self.get_document(document_id, user_id)
        document.status = DocumentStatus.FAILED
        document.stage_message = "已取消"
        document.error_message = "用户取消了处理"
        await self.session.flush()
        return to_document_out(document)

    # ------------------------------------------------------------------ #
    async def _require_kb(self, kb_id: int, user_id: int | None):  # noqa: ANN202
        kb = await self.kbs.get(kb_id)
        if kb is None or (user_id is not None and kb.user_id != user_id):
            raise NotFoundError("知识库不存在")
        return kb

    async def recover_unfinished(self) -> None:
        """服务启动时把中断的任务重新排队。"""
        pending = await self.documents.list_unfinished(limit=50)
        for document in pending:
            logger.info("恢复未完成的文档任务 id=%s file=%s", document.id, document.filename)
            schedule_ingestion(document.id, overwrite=True)
