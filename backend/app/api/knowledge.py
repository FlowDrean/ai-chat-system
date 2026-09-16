"""知识库路由：/api/knowledge-bases/*"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, get_current_user, pagination
from app.core.response import Envelope, ListEnvelope, ok, page
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import MessageResponse
from app.schemas.knowledge import (
    KnowledgeBaseCreate,
    KnowledgeBaseDetail,
    KnowledgeBaseOut,
    KnowledgeBaseUpdate,
    RetrievalTestRequest,
)
from app.services.knowledge_service import KnowledgeService

router = APIRouter(prefix="/knowledge-bases", tags=["知识库"])


@router.get("", response_model=ListEnvelope[KnowledgeBaseOut], summary="知识库列表")
async def list_knowledge_bases(
    keyword: str | None = Query(None),
    page_params: Pagination = Depends(pagination),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await KnowledgeService(db).list_knowledge_bases(
        user.id, keyword=keyword, page=page_params.page, page_size=page_params.page_size
    )
    return ok(page([item.model_dump() for item in items], total, page_params.page, page_params.page_size))


@router.post("", response_model=Envelope[KnowledgeBaseOut], summary="新建知识库")
async def create_knowledge_base(
    payload: KnowledgeBaseCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    kb = await KnowledgeService(db).create_knowledge_base(payload, user.id)
    await db.commit()
    return ok(kb, "知识库创建成功")


@router.get("/{kb_id}", response_model=Envelope[KnowledgeBaseDetail], summary="知识库详情（含文档列表）")
async def get_knowledge_base(
    kb_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    detail = await KnowledgeService(db).get_detail(kb_id, user.id)
    return ok(detail)


@router.put("/{kb_id}", response_model=Envelope[KnowledgeBaseOut], summary="编辑知识库")
async def update_knowledge_base(
    kb_id: int,
    payload: KnowledgeBaseUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    kb = await KnowledgeService(db).update_knowledge_base(kb_id, payload, user.id)
    await db.commit()
    return ok(kb, "知识库已更新")


@router.delete("/{kb_id}", response_model=Envelope[MessageResponse], summary="删除知识库")
async def delete_knowledge_base(
    kb_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await KnowledgeService(db).delete_knowledge_base(kb_id, user.id)
    await db.commit()
    return ok(MessageResponse(message="知识库已删除"))


@router.post("/{kb_id}/retrieval-test", response_model=Envelope[dict], summary="检索测试")
async def retrieval_test(
    kb_id: int,
    payload: RetrievalTestRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    result = await KnowledgeService(db).test_retrieval(kb_id, user.id, payload.query, payload.top_k)
    return ok(result, f"检索完成，命中 {len(result['chunks'])} 条")


@router.get("/{kb_id}/embedding-check", response_model=Envelope[dict], summary="校验 Embedding 配置")
async def embedding_check(
    kb_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = KnowledgeService(db)
    kb = await service.get_knowledge_base(kb_id, user.id)
    dimension = await service.verify_embedding_config(kb)
    return ok({"provider": kb.embedding_provider, "model": kb.embedding_model, "dimension": dimension})
