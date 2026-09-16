"""文档路由：/api/knowledge-bases/{id}/documents、/api/documents/*"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, get_current_user, pagination
from app.core.config import settings
from app.core.response import Envelope, ListEnvelope, ok, page
from app.db.session import get_db
from app.models.user import User
from app.rag.loader import SUPPORTED_EXTENSIONS
from app.schemas.common import MessageResponse
from app.schemas.knowledge import DocumentChunkOut, DocumentDetail, DocumentOut
from app.services.document_service import DocumentService

router = APIRouter(tags=["文档管理"])


@router.get(
    "/knowledge-bases/{kb_id}/documents",
    response_model=ListEnvelope[DocumentOut],
    summary="知识库文档列表",
)
async def list_documents(
    kb_id: int,
    status: str | None = Query(None, description="pending/parsing/splitting/embedding/completed/failed"),
    keyword: str | None = Query(None),
    page_params: Pagination = Depends(pagination),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await DocumentService(db).list_documents(
        kb_id,
        user.id,
        status=status,
        keyword=keyword,
        page=page_params.page,
        page_size=page_params.page_size,
    )
    return ok(page([item.model_dump() for item in items], total, page_params.page, page_params.page_size))


@router.post(
    "/knowledge-bases/{kb_id}/documents",
    response_model=Envelope[DocumentOut],
    summary="上传文档（PDF/DOCX/TXT/MD/CSV/XLSX）",
)
async def upload_document(
    kb_id: int,
    file: UploadFile = File(..., description="待上传的文档"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    document = await DocumentService(db).upload_document(kb_id, file, user.id)
    return ok(document, "文件已上传，正在后台解析与向量化")


@router.get("/documents", response_model=ListEnvelope[dict], summary="全部文档（管理后台）")
async def list_all_documents(
    status: str | None = Query(None),
    keyword: str | None = Query(None),
    page_params: Pagination = Depends(pagination),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await DocumentService(db).list_all_documents(
        None if user.is_admin else user.id,
        status=status,
        keyword=keyword,
        page=page_params.page,
        page_size=page_params.page_size,
    )
    return ok(page(items, total, page_params.page, page_params.page_size))


@router.get("/documents/{document_id}", response_model=Envelope[DocumentDetail], summary="文档详情（含分块预览）")
async def get_document(
    document_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    detail = await DocumentService(db).get_detail(document_id, None if user.is_admin else user.id)
    return ok(detail)


@router.get(
    "/documents/{document_id}/chunks",
    response_model=ListEnvelope[DocumentChunkOut],
    summary="文档分块列表",
)
async def list_chunks(
    document_id: int,
    page_params: Pagination = Depends(pagination),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from app.repositories.knowledge_repo import DocumentChunkRepository

    service = DocumentService(db)
    await service.get_document(document_id, None if user.is_admin else user.id)
    chunks = await DocumentChunkRepository(db).list_by_document(document_id, limit=500)
    offset = (page_params.page - 1) * page_params.page_size
    sliced = chunks[offset : offset + page_params.page_size]
    items = [
        {
            "id": c.id,
            "document_id": c.document_id,
            "chunk_index": c.chunk_index,
            "content": c.content,
            "token_count": c.token_count,
            "meta": c.meta,
            "score": c.score,
        }
        for c in sliced
    ]
    return ok(page(items, len(chunks), page_params.page, page_params.page_size))


@router.delete("/documents/{document_id}", response_model=Envelope[MessageResponse], summary="删除文档")
async def delete_document(
    document_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await DocumentService(db).delete_document(document_id, None if user.is_admin else user.id)
    return ok(MessageResponse(message="文档已删除"))


@router.post("/documents/{document_id}/reindex", response_model=Envelope[DocumentOut], summary="重新向量化")
async def reindex_document(
    document_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    document = await DocumentService(db).reindex_document(document_id, None if user.is_admin else user.id)
    return ok(document, "已加入重新向量化队列")


@router.get("/documents/meta/supported-types", response_model=Envelope[list[str]], summary="支持的文档类型")
async def supported_types(_: User = Depends(get_current_user)) -> dict:
    return ok(sorted(set(SUPPORTED_EXTENSIONS)))


@router.get("/documents/meta/limits", response_model=Envelope[dict], summary="上传限制")
async def upload_limits(_: User = Depends(get_current_user)) -> dict:
    return ok(
        {
            "max_upload_size_mb": settings.max_upload_size_mb,
            "allowed_extensions": sorted(settings.allowed_extension_set),
        }
    )
