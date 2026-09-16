"""聊天 / 会话路由：/api/chat、/api/conversations/*"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import Pagination, get_current_user, pagination
from app.core.response import Envelope, ListEnvelope, ok, page
from app.db.session import get_db
from app.models.user import User
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationCreate,
    ConversationOut,
    ConversationUpdate,
    MessageOut,
)
from app.schemas.common import MessageResponse
from app.services.chat_service import ChatService, to_conversation_out

router = APIRouter(tags=["AI 聊天"])


@router.post("/chat", response_model=Envelope[ChatResponse], summary="聊天（非流式）")
async def chat(
    payload: ChatRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = ChatService(db, user.id)
    result = await service.chat(payload)
    return ok(result)


@router.post(
    "/chat/stream",
    summary="聊天（SSE 流式）",
    response_class=StreamingResponse,
    responses={
        200: {
            "content": {"text/event-stream": {"example": 'data: {"type":"token","content":"你好"}\n\n'}},
            "description": "Server-Sent Events 流",
        }
    },
)
async def chat_stream(
    payload: ChatRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    service = ChatService(db, user.id)
    generator = service.stream_chat(payload)

    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Nginx 反代下关闭缓冲，保证实时性
        },
    )


# --------------------------------------------------------------------------- #
# 会话
# --------------------------------------------------------------------------- #
@router.get("/conversations", response_model=ListEnvelope[ConversationOut], summary="会话列表")
async def list_conversations(
    keyword: str | None = Query(None, description="按标题搜索"),
    favorite: bool | None = Query(None),
    archived: bool | None = Query(None, description="默认只返回未归档会话"),
    page_params: Pagination = Depends(pagination),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    items, total = await ChatService(db, user.id).list_conversations(
        keyword=keyword,
        favorite=favorite,
        archived=archived,
        page=page_params.page,
        page_size=page_params.page_size,
    )
    return ok(page([item.model_dump() for item in items], total, page_params.page, page_params.page_size))


@router.post("/conversations", response_model=Envelope[ConversationOut], summary="新建会话")
async def create_conversation(
    payload: ConversationCreate | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    conversation = await ChatService(db, user.id).create_conversation(payload)
    return ok(conversation, "会话已创建")


@router.get("/conversations/{conversation_id}", response_model=Envelope[ConversationOut], summary="会话详情")
async def get_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    conversation = await ChatService(db, user.id).get_conversation(conversation_id)
    return ok(to_conversation_out(conversation))


@router.put("/conversations/{conversation_id}", response_model=Envelope[ConversationOut], summary="更新会话")
async def update_conversation(
    conversation_id: int,
    payload: ConversationUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    conversation = await ChatService(db, user.id).update_conversation(conversation_id, payload)
    return ok(conversation, "会话已更新")


@router.delete("/conversations/{conversation_id}", response_model=Envelope[MessageResponse], summary="删除会话")
async def delete_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await ChatService(db, user.id).delete_conversation(conversation_id)
    return ok(MessageResponse(message="会话已删除"))


@router.post(
    "/conversations/{conversation_id}/clear",
    response_model=Envelope[ConversationOut],
    summary="清空当前对话",
)
async def clear_conversation(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    conversation = await ChatService(db, user.id).clear_conversation(conversation_id)
    return ok(conversation, "对话已清空")


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=Envelope[list[MessageOut]],
    summary="会话消息列表",
)
async def list_messages(
    conversation_id: int,
    limit: int = Query(200, ge=1, le=1000),
    before_id: int | None = Query(None, description="只返回该消息 id 之前的消息（滚动加载）"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    messages = await ChatService(db, user.id).list_messages(conversation_id, limit=limit, before_id=before_id)
    return ok([message.model_dump() for message in messages])


@router.delete("/messages/{message_id}", response_model=Envelope[MessageResponse], summary="删除单条消息")
async def delete_message(
    message_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await ChatService(db, user.id).delete_message(message_id)
    return ok(MessageResponse(message="消息已删除"))
