"""Dashboard 统计服务（对应开发文档 §39）。"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.conversation import Conversation
from app.models.knowledge import KnowledgeBase
from app.models.message import Message, MessageRole
from app.models.usage import UsageSource
from app.repositories.chat_repo import ConversationRepository, MessageRepository
from app.repositories.knowledge_repo import (
    DocumentChunkRepository,
    DocumentRepository,
    KnowledgeBaseRepository,
)
from app.repositories.model_repo import ModelRepository
from app.repositories.prompt_repo import UsageRepository
from app.repositories.user_repo import UserRepository

logger = get_logger(__name__)


class DashboardService:
    """统计口径：

    * 普通用户：只能看到自己的数据；
    * 管理员：默认看全站数据（`scope=all`），也可以切到只看自己。
    """

    def __init__(self, session: AsyncSession, *, user_id: int, is_admin: bool = False) -> None:
        self.session = session
        self.user_id = user_id
        self.is_admin = is_admin

        self.conversations = ConversationRepository(session)
        self.messages = MessageRepository(session)
        self.usage = UsageRepository(session)
        self.kbs = KnowledgeBaseRepository(session)
        self.documents = DocumentRepository(session)
        self.chunks = DocumentChunkRepository(session)
        self.models = ModelRepository(session)
        self.users = UserRepository(session)

    # ------------------------------------------------------------------ #
    @property
    def scope_user_id(self) -> int | None:
        """None 表示全站（仅管理员）。"""
        return None if self.is_admin else self.user_id

    async def overview(self, *, days: int = 14) -> dict:
        today_start = datetime.combine(date.today(), datetime.min.time())
        tomorrow_start = today_start + timedelta(days=1)
        trend_start = today_start - timedelta(days=max(1, days) - 1)
        scope = self.scope_user_id

        # ------------------------- 今日指标 -------------------------
        stats = {
            "today_conversations": await self.conversations.count_created_between(
                today_start, tomorrow_start, scope
            ),
            "today_messages": await self.messages.count_created_between(today_start, tomorrow_start, scope),
            "today_tokens": await self.usage.sum_tokens_between(today_start, tomorrow_start, scope),
            "today_model_calls": await self.usage.count_by_source_between(
                today_start, tomorrow_start, UsageSource.CHAT, scope
            ),
            "today_retrievals": await self.usage.sum_retrieved_chunks_between(today_start, tomorrow_start, scope),
            # ------------------------- 累计指标 -------------------------
            "total_conversations": (
                await self.conversations.count_for_user(self.user_id)
                if scope
                else await self.conversations.count()
            ),
            "total_messages": (
                await self.messages.count() if scope is None else await self._count_user_messages(scope)
            ),
            "total_tokens": (
                await self.messages.sum_tokens() if scope is None else await self.messages.sum_tokens()
            ),
            "model_count": await self.models.count_all(),
            "enabled_model_count": await self.models.count_enabled(),
            "knowledge_base_count": (
                await self.kbs.count() if scope is None else await self.kbs.count(KnowledgeBase.user_id == scope)
            ),
            "document_count": await self.documents.count_all(),
            "chunk_count": await self.chunks.count_all(),
            "user_count": await self.users.count_all(),
        }

        # ------------------------- 趋势 -------------------------
        trend_rows = {row["date"]: row for row in await self.usage.daily_trend(trend_start, tomorrow_start, scope)}
        conv_by_day = await self._daily_counts(Conversation, trend_start, tomorrow_start, scope)
        msg_by_day = await self._daily_counts(Message, trend_start, tomorrow_start, scope, only_user=True)

        trends = []
        for offset in range(max(1, days)):
            day = (trend_start + timedelta(days=offset)).date()
            key = day.isoformat()
            row = trend_rows.get(key, {})
            trends.append(
                {
                    "date": key,
                    "conversations": conv_by_day.get(key, 0),
                    "messages": msg_by_day.get(key, 0),
                    "tokens": int(row.get("tokens", 0)),
                    "model_calls": int(row.get("calls", 0)),
                }
            )

        # ------------------------- 分布 -------------------------
        model_usage = await self.usage.model_distribution(trend_start, tomorrow_start, scope)
        knowledge_rows = await self.usage.knowledge_distribution(trend_start, tomorrow_start, scope)
        kb_names = dict(await self.kbs.names_for_user(self.user_id))
        knowledge_usage = [
            {"name": kb_names.get(row["kb_id"], f"知识库 {row['kb_id']}"), "value": row["value"]}
            for row in knowledge_rows
        ]

        recent = await self.conversations.recent(scope, limit=5)

        return {
            "stats": stats,
            "trends": trends,
            "model_usage": [{"name": r["name"], "value": r["value"]} for r in model_usage],
            "knowledge_usage": knowledge_usage,
            "recent_conversations": [
                {
                    "id": c.id,
                    "title": c.title,
                    "message_count": c.message_count,
                    "total_tokens": c.total_tokens,
                    "updated_at": c.updated_at,
                }
                for c in recent
            ],
        }

    # ------------------------------------------------------------------ #
    async def _daily_counts(
        self,
        model: type,
        start: datetime,
        end: datetime,
        user_id: int | None,
        *,
        only_user: bool = False,
    ) -> dict[str, int]:
        """按天统计消息 / 会话数量（消息只统计 user 角色，避免与助手消息重复）。"""
        date_col = func.date(model.created_at)
        stmt = select(date_col.label("day"), func.count().label("cnt")).where(
            model.created_at >= start, model.created_at < end
        )
        if only_user:
            stmt = stmt.where(model.role == MessageRole.USER)
        if user_id is not None:
            if model is Conversation:
                stmt = stmt.where(Conversation.user_id == user_id)
            else:
                stmt = stmt.join(Conversation, Conversation.id == model.conversation_id).where(
                    Conversation.user_id == user_id
                )
        stmt = stmt.group_by(date_col).order_by(date_col)
        rows = (await self.session.execute(stmt)).all()
        return {str(row.day): int(row.cnt) for row in rows}

    async def _count_user_messages(self, user_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(Message)
            .join(Conversation, Conversation.id == Message.conversation_id)
            .where(Conversation.user_id == user_id)
        )
        return int((await self.session.execute(stmt)).scalar_one() or 0)
