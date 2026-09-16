"""会话 / 消息仓储。"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence

from sqlalchemy import func, or_, select

from app.models.conversation import Conversation
from app.models.message import Message, MessageRole
from app.repositories.base import BaseRepository


class ConversationRepository(BaseRepository[Conversation]):
    model = Conversation
    not_found_message = "会话不存在"

    async def get_owned(self, conversation_id: int, user_id: int) -> Conversation | None:
        return await self.find_one(Conversation.id == conversation_id, Conversation.user_id == user_id)

    async def list_conversations(
        self,
        user_id: int,
        *,
        keyword: str | None = None,
        favorite: bool | None = None,
        archived: bool | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[Conversation], int]:
        where = [Conversation.user_id == user_id]
        if keyword:
            where.append(Conversation.title.like(f"%{keyword.strip()}%"))
        if favorite is not None:
            where.append(Conversation.is_favorite.is_(favorite))
        if archived is not None:
            where.append(Conversation.is_archived.is_(archived))
        return await self.paginate(
            *where,
            order_by=[Conversation.updated_at.desc(), Conversation.id.desc()],
            offset=offset,
            limit=limit,
        )

    async def count_for_user(self, user_id: int) -> int:
        return await self.count(Conversation.user_id == user_id)

    async def sum_tokens_for_user(self, user_id: int) -> int:
        stmt = select(func.coalesce(func.sum(Conversation.total_tokens), 0)).where(Conversation.user_id == user_id)
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def count_created_between(self, start: datetime, end: datetime, user_id: int | None = None) -> int:
        where = [Conversation.created_at >= start, Conversation.created_at < end]
        if user_id is not None:
            where.append(Conversation.user_id == user_id)
        return await self.count(*where)

    async def recent(self, user_id: int | None = None, limit: int = 5) -> list[Conversation]:
        where = [] if user_id is None else [Conversation.user_id == user_id]
        return await self.list_all(
            *where, order_by=[Conversation.updated_at.desc()], limit=limit
        )


class MessageRepository(BaseRepository[Message]):
    model = Message
    not_found_message = "消息不存在"

    async def list_by_conversation(
        self,
        conversation_id: int,
        *,
        limit: int | None = None,
        desc: bool = False,
        roles: Sequence[str] | None = None,
    ) -> list[Message]:
        where = [Message.conversation_id == conversation_id]
        if roles:
            where.append(Message.role.in_(list(roles)))
        order = Message.id.desc() if desc else Message.id.asc()
        items = await self.list_all(*where, order_by=[order], limit=limit)
        return list(reversed(items)) if desc and items else items

    async def list_context(
        self, conversation_id: int, *, max_messages: int = 20, system_only: bool = False
    ) -> list[Message]:
        """取最近 N 条消息，用于构造 LLM 上下文。"""
        return await self.list_by_conversation(
            conversation_id,
            limit=max_messages,
            desc=True,
            roles=(MessageRole.SYSTEM,) if system_only else None,
        )

    async def last_assistant(self, conversation_id: int) -> Message | None:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id, Message.role == MessageRole.ASSISTANT)
            .order_by(Message.id.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def last_user(self, conversation_id: int) -> Message | None:
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id, Message.role == MessageRole.USER)
            .order_by(Message.id.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def delete_after(self, conversation_id: int, message_id: int) -> int:
        from sqlalchemy import delete as sa_delete

        result = await self.session.execute(
            sa_delete(Message).where(Message.conversation_id == conversation_id, Message.id > message_id)
        )
        await self.session.flush()
        return int(result.rowcount or 0)

    async def count_by_conversation(self, conversation_id: int) -> int:
        return await self.count(Message.conversation_id == conversation_id)

    async def count_created_between(self, start: datetime, end: datetime, user_id: int | None = None) -> int:
        stmt = select(func.count()).select_from(Message).where(Message.created_at >= start, Message.created_at < end)
        if user_id is not None:
            stmt = stmt.join(Conversation, Conversation.id == Message.conversation_id).where(
                Conversation.user_id == user_id
            )
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def sum_tokens(self, start: datetime | None = None, end: datetime | None = None) -> int:
        stmt = select(func.coalesce(func.sum(Message.total_tokens), 0))
        if start is not None:
            stmt = stmt.where(Message.created_at >= start)
        if end is not None:
            stmt = stmt.where(Message.created_at < end)
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def search_content(self, conversation_id: int, keyword: str) -> list[Message]:
        return await self.list_all(
            Message.conversation_id == conversation_id,
            or_(Message.content.like(f"%{keyword}%")),
            order_by=[Message.id.asc()],
            limit=50,
        )
