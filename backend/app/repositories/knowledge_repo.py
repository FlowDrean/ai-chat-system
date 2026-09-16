"""知识库 / 文档 / 分块仓储。"""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, or_, select

from app.models.document import Document, DocumentChunk, DocumentStatus
from app.models.knowledge import KnowledgeBase
from app.repositories.base import BaseRepository


class KnowledgeBaseRepository(BaseRepository[KnowledgeBase]):
    model = KnowledgeBase
    not_found_message = "知识库不存在"

    async def get_owned(self, kb_id: int, user_id: int) -> KnowledgeBase | None:
        return await self.find_one(KnowledgeBase.id == kb_id, KnowledgeBase.user_id == user_id)

    async def list_for_user(
        self,
        user_id: int,
        *,
        keyword: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[KnowledgeBase], int]:
        where = [KnowledgeBase.user_id == user_id]
        if keyword:
            like = f"%{keyword.strip()}%"
            where.append(or_(KnowledgeBase.name.like(like), KnowledgeBase.description.like(like)))
        return await self.paginate(
            *where, order_by=[KnowledgeBase.updated_at.desc()], offset=offset, limit=limit
        )

    async def names_for_user(self, user_id: int) -> list[tuple[int, str]]:
        stmt = select(KnowledgeBase.id, KnowledgeBase.name).where(KnowledgeBase.user_id == user_id)
        result = await self.session.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def count_all(self) -> int:
        return await self.count()

    async def recalculate_counts(self, kb_id: int) -> None:
        doc_count_stmt = select(func.count()).select_from(Document).where(Document.knowledge_base_id == kb_id)
        chunk_count_stmt = select(func.count()).select_from(DocumentChunk).where(
            DocumentChunk.knowledge_base_id == kb_id
        )
        doc_count = int((await self.session.execute(doc_count_stmt)).scalar_one() or 0)
        chunk_count = int((await self.session.execute(chunk_count_stmt)).scalar_one() or 0)
        kb = await self.get(kb_id)
        if kb is not None:
            kb.document_count = doc_count
            kb.chunk_count = chunk_count
            await self.session.flush()


class DocumentRepository(BaseRepository[Document]):
    model = Document
    not_found_message = "文档不存在"

    async def list_by_kb(
        self,
        kb_id: int,
        *,
        status: str | None = None,
        keyword: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Document], int]:
        where = [Document.knowledge_base_id == kb_id]
        if status:
            where.append(Document.status == status)
        if keyword:
            where.append(Document.filename.like(f"%{keyword.strip()}%"))
        return await self.paginate(*where, order_by=[Document.id.desc()], offset=offset, limit=limit)

    async def get_owned(self, document_id: int, user_id: int | None) -> Document | None:
        where = [Document.id == document_id]
        if user_id is not None:
            where.append(Document.user_id == user_id)
        return await self.find_one(*where)

    async def find_duplicate(self, kb_id: int, file_hash: str) -> Document | None:
        return await self.find_one(Document.knowledge_base_id == kb_id, Document.file_hash == file_hash)

    async def count_all(self) -> int:
        return await self.count()

    async def count_in_progress(self) -> int:
        return await self.count(
            Document.status.in_(
                [
                    DocumentStatus.PENDING,
                    DocumentStatus.PARSING,
                    DocumentStatus.SPLITTING,
                    DocumentStatus.EMBEDDING,
                ]
            )
        )

    async def list_unfinished(self, limit: int = 20) -> list[Document]:
        """服务重启后，恢复中断的处理任务。"""
        return await self.list_all(
            Document.status.in_(
                [
                    DocumentStatus.PENDING,
                    DocumentStatus.PARSING,
                    DocumentStatus.SPLITTING,
                    DocumentStatus.EMBEDDING,
                ]
            ),
            order_by=[Document.id.asc()],
            limit=limit,
        )


class DocumentChunkRepository(BaseRepository[DocumentChunk]):
    model = DocumentChunk
    not_found_message = "文档分块不存在"

    async def list_by_document(self, document_id: int, limit: int = 200) -> list[DocumentChunk]:
        return await self.list_all(
            DocumentChunk.document_id == document_id, order_by=[DocumentChunk.chunk_index.asc()], limit=limit
        )

    async def list_by_kb(self, kb_id: int, limit: int = 5000) -> list[DocumentChunk]:
        return await self.list_all(
            DocumentChunk.knowledge_base_id == kb_id, order_by=[DocumentChunk.id.asc()], limit=limit
        )

    async def list_with_embeddings(self, kb_id: int, limit: int = 20000) -> Sequence[DocumentChunk]:
        stmt = (
            select(DocumentChunk)
            .where(DocumentChunk.knowledge_base_id == kb_id, DocumentChunk.embedding.is_not(None))
            .order_by(DocumentChunk.id.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def delete_by_document(self, document_id: int) -> int:
        result = await self.session.execute(sa_delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
        await self.session.flush()
        return int(result.rowcount or 0)

    async def delete_by_kb(self, kb_id: int) -> int:
        result = await self.session.execute(sa_delete(DocumentChunk).where(DocumentChunk.knowledge_base_id == kb_id))
        await self.session.flush()
        return int(result.rowcount or 0)

    async def delete_from_index(self, document_id: int, from_index: int) -> int:
        result = await self.session.execute(
            sa_delete(DocumentChunk).where(
                DocumentChunk.document_id == document_id, DocumentChunk.chunk_index >= from_index
            )
        )
        await self.session.flush()
        return int(result.rowcount or 0)

    async def count_by_kb(self, kb_id: int) -> int:
        return await self.count(DocumentChunk.knowledge_base_id == kb_id)

    async def count_all(self) -> int:
        return await self.count()
