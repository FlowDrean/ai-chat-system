"""聊天服务：会话 / 消息 / 上下文构造 / LangGraph 流式回答 / 持久化。

一次完整的流式请求：

    前端 POST /api/chat/stream
        ↓
    1. 解析会话、模型、知识库、Prompt、参数
    2. 保存用户消息
    3. 预创建助手消息（status=streaming）
    4. 构造上下文（System + 历史消息 + 当前问题）
    5. LangGraph：route →（RAG 检索）→ LLM 流式生成
        ↓ 每个 token 立刻 SSE 推给前端
    6. 落库助手消息（内容 / Token / 耗时 / 引用来源）
    7. 记录调用日志（usage_logs）
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator
from datetime import datetime
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BadRequestError, NotFoundError
from app.core.logging import get_logger
from app.graph.state import ChatDeps, EventType
from app.graph.workflow import run_graph, stream_graph
from app.llm.factory import build_runtime_config, create_llm
from app.models.conversation import Conversation
from app.models.document import DocumentStatus
from app.models.knowledge import KnowledgeBase
from app.models.message import Message, MessageRole, MessageStatus
from app.models.model_config import ModelConfig
from app.models.usage import UsageSource
from app.rag.prompts import DEFAULT_RAG_SYSTEM_PROMPT, DEFAULT_SYSTEM_PROMPT
from app.repositories.chat_repo import ConversationRepository, MessageRepository
from app.repositories.knowledge_repo import DocumentRepository, KnowledgeBaseRepository
from app.repositories.prompt_repo import PromptRepository, UsageRepository
from app.schemas.chat import (
    ChatParams,
    ChatRequest,
    ChatResponse,
    ConversationCreate,
    ConversationOut,
    ConversationUpdate,
    MessageOut,
)
from app.services.model_service import ModelService
from app.mcp.bridge import build_mcp_tools_with_meta
from app.services.mcp_service import McpService
from app.services.skill_service import SkillService
from app.skills.registry import build_tools, tool_name_for

logger = get_logger(__name__)


def sse(data: dict[str, Any]) -> str:
    """SSE 帧格式。"""
    return f"data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def to_conversation_out(conversation: Conversation) -> ConversationOut:
    return ConversationOut.model_validate(conversation.to_dict())


def to_message_out(message: Message) -> MessageOut:
    return MessageOut.model_validate(message.to_dict())


@dataclass
class ChatRuntime:
    conversation: Conversation
    model: ModelConfig
    system_prompt: str
    history: list[BaseMessage]
    params: dict[str, Any]
    question: str = ""
    knowledge_base: KnowledgeBase | None = None
    use_rag: bool = False
    user_message: Message | None = None
    assistant_message: Message | None = None
    notices: list[str] = field(default_factory=list)
    # 技能：本次对话启用的技能行 + 对应的 LangChain 工具 + 工具名到技能元信息的映射
    skills: list[Any] = field(default_factory=list)
    tools: list[Any] = field(default_factory=list)
    skill_meta: dict[str, Any] = field(default_factory=dict)
    mcp_servers: list[Any] = field(default_factory=list)


class ChatService:
    def __init__(self, session: AsyncSession, user_id: int) -> None:
        self.session = session
        self.user_id = user_id
        self.conversations = ConversationRepository(session)
        self.messages = MessageRepository(session)
        self.models = ModelService(session)
        self.kbs = KnowledgeBaseRepository(session)
        self.documents = DocumentRepository(session)
        self.prompts = PromptRepository(session)
        self.usage = UsageRepository(session)

    # ------------------------------------------------------------------ #
    # 会话管理
    # ------------------------------------------------------------------ #
    async def create_conversation(self, data: ConversationCreate | None = None) -> ConversationOut:
        data = data or ConversationCreate()
        model = await self.models.resolve_for_chat(data.model_id)
        kb = await self._resolve_kb(data.knowledge_base_id)
        prompt_id = await self._validate_prompt(data.prompt_id)

        conversation = Conversation(
            user_id=self.user_id,
            title=(data.title or "新对话").strip() or "新对话",
            model_id=model.id,
            knowledge_base_id=kb.id if kb else None,
            prompt_id=prompt_id,
            system_prompt=data.system_prompt,
            params=(data.params.model_dump(exclude_none=True) if data.params else {"streaming": True}),
        )
        self.session.add(conversation)
        await self.session.flush()
        await self.session.commit()
        return to_conversation_out(conversation)

    async def list_conversations(
        self,
        *,
        keyword: str | None = None,
        favorite: bool | None = None,
        archived: bool | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[ConversationOut], int]:
        items, total = await self.conversations.list_conversations(
            self.user_id,
            keyword=keyword,
            favorite=favorite,
            archived=archived if archived is not None else False,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return [to_conversation_out(c) for c in items], total

    async def get_conversation(self, conversation_id: int) -> Conversation:
        conversation = await self.conversations.get_owned(conversation_id, self.user_id)
        if conversation is None:
            raise NotFoundError("会话不存在")
        return conversation

    async def update_conversation(self, conversation_id: int, data: ConversationUpdate) -> ConversationOut:
        conversation = await self.get_conversation(conversation_id)
        payload = data.model_dump(exclude_unset=True)

        if "model_id" in payload and payload["model_id"]:
            model = await self.models.resolve_for_chat(payload["model_id"])
            conversation.model_id = model.id
        if "knowledge_base_id" in payload:
            kb = await self._resolve_kb(payload["knowledge_base_id"])
            conversation.knowledge_base_id = kb.id if kb else None
        if "prompt_id" in payload:
            conversation.prompt_id = await self._validate_prompt(payload["prompt_id"])
        if data.params is not None:
            conversation.params = {**data.params.model_dump(exclude_none=True)}
        if data.system_prompt is not None:
            conversation.system_prompt = data.system_prompt or None

        for key in ("title", "is_favorite", "is_archived"):
            if key in payload and payload[key] is not None:
                setattr(conversation, key, payload[key])

        await self.session.flush()
        await self.session.commit()
        return to_conversation_out(conversation)

    async def delete_conversation(self, conversation_id: int) -> None:
        conversation = await self.get_conversation(conversation_id)
        await self.conversations.delete(conversation)
        await self.session.commit()
        logger.info("删除会话 id=%s", conversation_id)

    async def clear_conversation(self, conversation_id: int) -> ConversationOut:
        """清空当前对话（保留会话本身）。"""
        conversation = await self.get_conversation(conversation_id)
        for message in await self.messages.list_by_conversation(conversation_id):
            await self.messages.delete(message)
        conversation.message_count = 0
        conversation.total_tokens = 0
        conversation.summary = None
        conversation.title = "新对话"
        await self.session.flush()
        await self.session.commit()
        return to_conversation_out(conversation)

    async def list_messages(
        self, conversation_id: int, *, limit: int = 200, before_id: int | None = None
    ) -> list[MessageOut]:
        await self.get_conversation(conversation_id)
        messages = await self.messages.list_by_conversation(conversation_id, limit=limit)
        if before_id is not None:
            messages = [m for m in messages if m.id < before_id]
        return [to_message_out(m) for m in messages]

    async def delete_message(self, message_id: int) -> None:
        """删除单条消息（用户重新编辑时使用）。"""
        message = await self.messages.get_or_404(message_id)
        conversation = await self.get_conversation(message.conversation_id)
        deleted_after = await self.messages.delete_after(conversation.id, message.id)
        await self.messages.delete(message)
        conversation.message_count = max(0, conversation.message_count - deleted_after - 1)
        await self.session.flush()
        await self.session.commit()

    # ------------------------------------------------------------------ #
    # 聊天准备
    # ------------------------------------------------------------------ #
    async def _resolve_kb(self, kb_id: int | None) -> KnowledgeBase | None:
        if not kb_id:  # None 或 0 表示不使用知识库
            return None
        kb = await self.kbs.get_owned(kb_id, self.user_id)
        if kb is None:
            raise NotFoundError("知识库不存在或无权访问")
        return kb

    async def _validate_prompt(self, prompt_id: int | None) -> int | None:
        if not prompt_id:
            return None
        prompt = await self.prompts.get_visible(prompt_id, self.user_id)
        if prompt is None:
            raise NotFoundError("Prompt 不存在")
        return prompt.id

    async def _get_or_create_conversation(self, request: ChatRequest) -> Conversation:
        if request.conversation_id:
            return await self.get_conversation(request.conversation_id)
        model = await self.models.resolve_for_chat(request.model_id)
        kb = await self._resolve_kb(request.knowledge_base_id)
        conversation = Conversation(
            user_id=self.user_id,
            title="新对话",
            model_id=model.id,
            knowledge_base_id=kb.id if kb else None,
            prompt_id=await self._validate_prompt(request.prompt_id),
            system_prompt=request.system_prompt,
            params=(request.params.model_dump(exclude_none=True) if request.params else {"streaming": True}),
        )
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    def _build_history(self, messages: list[Message], question: str) -> tuple[list[BaseMessage], list[Message]]:
        """把历史消息转成 LangChain 消息，并按 token/条数预算裁剪。

        返回 `(消息列表, 被裁掉的消息)`。
        """
        candidates: list[BaseMessage] = []
        source: list[Message] = []
        for message in messages:
            if message.role == MessageRole.USER and message.content:
                candidates.append(HumanMessage(content=message.content))
                source.append(message)
            elif message.role == MessageRole.ASSISTANT and message.content and message.status != MessageStatus.ERROR:
                candidates.append(AIMessage(content=message.content))
                source.append(message)

        max_messages = max(2, settings.max_context_messages)
        dropped: list[Message] = []
        if len(candidates) > max_messages:
            dropped = source[: len(candidates) - max_messages]
            candidates = candidates[-max_messages:]
            source = source[-max_messages:]

        # 字符预算裁剪（中文场景下 1 token ≈ 1 字，保守按 1.5 字符/token 估算）
        budget = max(2000, settings.max_context_chars)
        total = sum(len(m.content if isinstance(m.content, str) else "") for m in candidates)
        while candidates and total > budget:
            removed = candidates.pop(0)
            dropped.append(source.pop(0))
            total -= len(removed.content if isinstance(removed.content, str) else "")

        if question:
            candidates.append(HumanMessage(content=question))
        return candidates, dropped

    async def _resolve_system_prompt(
        self,
        conversation: Conversation,
        request: ChatRequest,
        kb: KnowledgeBase | None,
        use_rag: bool,
        question: str,
    ) -> tuple[str, str | None]:
        """返回 `(system_prompt, prompt_name)`。"""
        prompt_content: str | None = None
        prompt_name: str | None = None
        prompt_id = request.prompt_id if request.prompt_id is not None else conversation.prompt_id
        if prompt_id:
            prompt = await self.prompts.get_visible(prompt_id, self.user_id)
            if prompt is not None:
                prompt_content = prompt.content
                prompt_name = prompt.name
                prompt.usage_count = (prompt.usage_count or 0) + 1

        base = (
            request.system_prompt
            or prompt_content
            or conversation.system_prompt
            or (DEFAULT_RAG_SYSTEM_PROMPT if (kb and use_rag) else DEFAULT_SYSTEM_PROMPT)
        )
        # 变量渲染（context 由 LangGraph 在检索后填充）
        base = (
            base.replace("{{question}}", question)
            .replace("{question}", question)
            .replace("{{user_name}}", str(self.user_id))
            .replace("{{knowledge_base}}", kb.name if kb else "")
        )
        if conversation.summary:
            base = f"{base}\n\n【历史对话摘要】\n{conversation.summary}"
        return base, prompt_name

    async def prepare(self, request: ChatRequest) -> ChatRuntime:
        """准备一次聊天所需的全部上下文，并落库用户消息。"""
        conversation = await self._get_or_create_conversation(request)

        # ---------- 重新生成：复用最后一条用户消息，删掉上一条助手回复 ----------
        question = request.content
        if request.regenerate:
            last_user = await self.messages.last_user(conversation.id)
            if last_user is None:
                raise BadRequestError("没有可重新生成的问题")
            question = request.content or last_user.content
            last_assistant = await self.messages.last_assistant(conversation.id)
            if last_assistant is not None:
                await self.messages.delete(last_assistant)
                conversation.message_count = max(0, conversation.message_count - 1)
            user_message = last_user
        else:
            user_message = Message(
                conversation_id=conversation.id,
                role=MessageRole.USER,
                content=question,
                status=MessageStatus.DONE,
            )
            self.session.add(user_message)
            await self.session.flush()

        # ---------- 模型 ----------
        model_id = request.model_id if request.model_id is not None else conversation.model_id
        model = await self.models.resolve_for_chat(model_id)

        # ---------- 知识库 ----------
        kb_id = request.knowledge_base_id if request.knowledge_base_id is not None else conversation.knowledge_base_id
        knowledge_base = await self._resolve_kb(kb_id)
        use_rag = bool(knowledge_base) and (request.use_rag is not False)

        # ---------- 参数（会话级） ----------
        params = {**(conversation.params or {})}
        if request.params is not None:
            params.update(request.params.to_llm_overrides())
            params["streaming"] = request.params.streaming
        params.setdefault("streaming", True)

        # ---------- System Prompt ----------
        system_prompt, _ = await self._resolve_system_prompt(conversation, request, knowledge_base, use_rag, question)

        # ---------- 历史消息 ----------
        history_messages = await self.messages.list_by_conversation(conversation.id, limit=200)
        # 排除刚写入的这条用户消息（会作为 question 追加）
        history_messages = [m for m in history_messages if m.id != user_message.id]
        history, dropped = self._build_history(history_messages, question)

        # ---------- 技能 ----------
        skill_ids = request.skill_ids if request.skill_ids is not None else (conversation.skill_ids or [])
        skills = await SkillService(self.session).resolve_for_chat(list(skill_ids or []))
        skill_tools = build_tools(skills)
        skill_meta: dict[str, Any] = {
            tool_name_for(skill.slug, skill.id): {
                "id": skill.id,
                "name": skill.name,
                "type": skill.type,
                "source": "skill",
            }
            for skill in skills
        }

        # ---------- MCP 服务（与技能共用同一套 tool-calling 链路） ----------
        mcp_ids = (
            request.mcp_server_ids
            if request.mcp_server_ids is not None
            else (conversation.mcp_server_ids or [])
        )
        mcp_servers = await McpService(self.session).resolve_for_chat(list(mcp_ids or []))
        mcp_tools, mcp_meta = build_mcp_tools_with_meta(mcp_servers)
        skill_meta.update(mcp_meta)
        tools = [*skill_tools, *mcp_tools]

        # ---------- 会话设置回写 ----------
        conversation.model_id = model.id
        conversation.knowledge_base_id = knowledge_base.id if knowledge_base else None
        conversation.prompt_id = request.prompt_id if request.prompt_id is not None else conversation.prompt_id
        conversation.params = params
        conversation.skill_ids = [skill.id for skill in skills]
        conversation.mcp_server_ids = [server.id for server in mcp_servers]
        if request.system_prompt is not None:
            conversation.system_prompt = request.system_prompt
        conversation.message_count = (conversation.message_count or 0) + (0 if request.regenerate else 1)
        self._auto_title(conversation, question)

        # ---------- 预创建助手消息 ----------
        assistant_message = Message(
            conversation_id=conversation.id,
            role=MessageRole.ASSISTANT,
            content="",
            status=MessageStatus.STREAMING,
            model_id=model.id,
            model_name=model.model_name,
            provider=model.provider,
            knowledge_base_id=knowledge_base.id if knowledge_base else None,
        )
        self.session.add(assistant_message)
        await self.session.flush()
        await self.session.commit()

        if dropped:
            self._schedule_summary(conversation, dropped, model)

        return ChatRuntime(
            conversation=conversation,
            model=model,
            system_prompt=system_prompt,
            history=history,
            params=params,
            question=question,
            use_rag=use_rag,
            knowledge_base=knowledge_base,
            user_message=user_message,
            assistant_message=assistant_message,
            skills=skills,
            tools=tools,
            skill_meta=skill_meta,
            mcp_servers=mcp_servers,
        )

    @staticmethod
    def _auto_title(conversation: Conversation, question: str) -> None:
        if conversation.title in (None, "", "新对话") and question:
            title = " ".join(question.split())
            conversation.title = title[:30] + ("…" if len(title) > 30 else "")

    def _schedule_summary(self, conversation: Conversation, dropped: list[Message], model: ModelConfig) -> None:
        """后台生成历史摘要（不阻塞当前对话）。"""

        async def _run() -> None:
            from app.db.session import AsyncSessionLocal

            try:
                transcript = "\n".join(
                    f"{'用户' if m.role == MessageRole.USER else 'AI'}：{m.content[:400]}"
                    for m in dropped[-12:]
                    if m.content
                )
                if not transcript.strip():
                    return
                llm = create_llm(build_runtime_config(model, {"temperature": 0.2, "max_tokens": 300}, streaming=False))
                prompt = (
                    "请把下面的对话历史压缩成不超过 200 字的中文摘要，保留关键事实、结论与用户偏好，不要编造：\n\n"
                    f"{transcript}"
                )
                result = await llm.ainvoke([HumanMessage(content=prompt)])
                summary = result.content if isinstance(result.content, str) else str(result.content)
                async with AsyncSessionLocal() as session:
                    target = await ConversationRepository(session).get(conversation.id)
                    if target is not None:
                        target.summary = (summary or "").strip()[:2000] or target.summary
                        await session.commit()
                logger.info("会话 %s 历史摘要已更新", conversation.id)
            except Exception as exc:  # noqa: BLE001 - 摘要失败不影响主流程
                logger.info("历史摘要生成失败（忽略）：%s", exc)

        task = asyncio.create_task(_run())
        task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

    # ------------------------------------------------------------------ #
    # 流式聊天
    # ------------------------------------------------------------------ #
    async def stream_chat(self, request: ChatRequest) -> AsyncIterator[str]:
        """SSE 流式聊天。

        停止生成 / 客户端断开的处理策略：

        * 生成在后台任务中运行，token 实时推给前端；
        * 连接断开时，`stream_graph` 会取消生成任务并抛出 CancelledError；
        * 此时**不能**在响应协程里 await 数据库（响应任务正在被销毁，任何 await
          都会被取消，导致消息状态停留在 streaming），因此改为投递一个
          「独立任务 + 独立数据库会话」来保存已生成的内容，状态标记为 stopped。
        """
        started = time.perf_counter()
        runtime = await self.prepare(request)
        assert runtime.assistant_message is not None

        conversation_id = runtime.conversation.id
        assistant_message_id = runtime.assistant_message.id
        events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        llm = create_llm(build_runtime_config(runtime.model, runtime.params, streaming=True))
        retriever = None
        if runtime.knowledge_base is not None:
            from app.rag.retriever import Retriever

            retriever = Retriever(self.session, runtime.knowledge_base)

        deps = ChatDeps(
            llm=llm,
            events=events,
            question=runtime.question,
            system_prompt=runtime.system_prompt,
            retriever=retriever,
            knowledge_base_id=runtime.knowledge_base.id if runtime.knowledge_base else None,
            knowledge_base_name=runtime.knowledge_base.name if runtime.knowledge_base else None,
            model_id=runtime.model.id,
            model_name=runtime.model.name,
            use_rag=runtime.use_rag,
            mcp_server_names=[server.name for server in runtime.mcp_servers],
            tools=runtime.tools,
            skill_meta=runtime.skill_meta,
        )

        answer_parts: list[str] = []
        sources: list[dict[str, Any]] = []
        skills_used: list[dict[str, Any]] = []
        usage: dict[str, int] = {}
        state: dict[str, Any] = {}
        failed = False
        persisted = False

        try:
            yield sse({"type": EventType.START})
            yield sse(
                {
                    "type": EventType.META,
                    "conversation": to_conversation_out(runtime.conversation).model_dump(),
                    "user_message": (
                        to_message_out(runtime.user_message).model_dump() if runtime.user_message else None
                    ),
                    "assistant_message": to_message_out(runtime.assistant_message).model_dump(),
                    "model": {
                        "id": runtime.model.id,
                        "name": runtime.model.name,
                        "provider": runtime.model.provider,
                        "model_name": runtime.model.model_name,
                    },
                    "knowledge_base": (
                        {"id": runtime.knowledge_base.id, "name": runtime.knowledge_base.name}
                        if runtime.knowledge_base
                        else None
                    ),
                    "use_rag": runtime.use_rag,
                }
            )

            async for event in stream_graph(deps, runtime.history):
                event_type = event.get("type")
                if event_type == EventType.TOKEN:
                    answer_parts.append(event.get("content", ""))
                elif event_type == EventType.SOURCES:
                    sources = event.get("sources") or []
                elif event_type == EventType.ERROR:
                    failed = True
                elif event_type == EventType.DONE:
                    state = event.get("state") or {}
                    usage = state.get("usage") or {}
                    sources = state.get("sources") or sources
                    skills_used = state.get("skills_used") or []
                    continue
                yield sse(event)

            # ------------------------------ 正常完成 ------------------------------
            answer = "".join(answer_parts) or (state.get("answer") or "")
            latency = (time.perf_counter() - started) * 1000
            status = MessageStatus.ERROR if (failed or state.get("error")) else MessageStatus.DONE

            message = await self._finalize_assistant(
                runtime,
                answer,
                sources,
                usage,
                latency,
                status=status,
                error_message=state.get("error"),
                skills=skills_used,
            )
            await self._record_usage(
                runtime, answer, usage, latency, len(sources), success=status != MessageStatus.ERROR
            )
            await self._touch_conversation(runtime.conversation, used_tokens=usage.get("total_tokens", 0))
            await self._mark_skills_used(skills_used)
            persisted = True

            yield sse(
                {
                    "type": EventType.DONE,
                    "message": message.model_dump(),
                    "conversation": to_conversation_out(runtime.conversation).model_dump(),
                    "usage": {
                        **usage,
                        "latency_ms": round(latency, 1),
                        "retrieved_chunks": len(sources),
                    },
                    "sources": sources,
                    "skills": skills_used,
                    "mcp_servers": [server.name for server in runtime.mcp_servers],
                    "route": state.get("route"),
                    "stopped": False,
                }
            )
        finally:
            if not persisted:
                # 用户停止生成 / 客户端断开：交给独立任务落库（不能 await）
                schedule_stopped_persist(
                    conversation_id=conversation_id,
                    message_id=assistant_message_id,
                    content="".join(answer_parts),
                    sources=sources,
                    skills=skills_used,
                    usage=usage,
                    latency_ms=(time.perf_counter() - started) * 1000,
                )

    # ------------------------------------------------------------------ #
    # 非流式聊天
    # ------------------------------------------------------------------ #
    async def chat(self, request: ChatRequest) -> ChatResponse:
        started = time.perf_counter()
        runtime = await self.prepare(request)
        assert runtime.assistant_message is not None

        events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        llm = create_llm(build_runtime_config(runtime.model, runtime.params, streaming=False))
        retriever = None
        if runtime.knowledge_base is not None:
            from app.rag.retriever import Retriever

            retriever = Retriever(self.session, runtime.knowledge_base)

        deps = ChatDeps(
            llm=llm,
            events=events,
            question=runtime.question,
            system_prompt=runtime.system_prompt,
            retriever=retriever,
            knowledge_base_id=runtime.knowledge_base.id if runtime.knowledge_base else None,
            knowledge_base_name=runtime.knowledge_base.name if runtime.knowledge_base else None,
            model_id=runtime.model.id,
            model_name=runtime.model.name,
            use_rag=runtime.use_rag,
            tools=runtime.tools,
            skill_meta=runtime.skill_meta,
        )
        state = await run_graph(deps, runtime.history)
        latency = (time.perf_counter() - started) * 1000
        sources = state.get("sources") or []
        skills_used = state.get("skills_used") or []
        usage = state.get("usage") or {}
        status = MessageStatus.ERROR if state.get("error") else MessageStatus.DONE

        message = await self._finalize_assistant(
            runtime,
            state.get("answer") or "",
            sources,
            usage,
            latency,
            status=status,
            error_message=state.get("error"),
            skills=skills_used,
        )
        await self._record_usage(
            runtime, state.get("answer") or "", usage, latency, len(sources), success=status != MessageStatus.ERROR
        )
        await self._touch_conversation(runtime.conversation, used_tokens=usage.get("total_tokens", 0))
        await self._mark_skills_used(skills_used)
        return ChatResponse(
            conversation_id=runtime.conversation.id,
            message=message,
            sources=sources,  # type: ignore[arg-type]
            skills=skills_used,  # type: ignore[arg-type]
            usage={**usage, "latency_ms": round(latency, 1), "retrieved_chunks": len(sources)},
            mcp_servers=[server.name for server in runtime.mcp_servers],  # type: ignore[call-arg]
        )

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #


    async def _finalize_assistant(
        self,
        runtime: ChatRuntime,
        answer: str,
        sources: list[dict[str, Any]],
        usage: dict[str, int],
        latency_ms: float,
        *,
        status: str,
        error_message: str | None = None,
        skills: list[dict[str, Any]] | None = None,
    ) -> MessageOut:
        message = runtime.assistant_message
        assert message is not None
        message.content = answer or ("（生成失败，未产生内容）" if status == MessageStatus.ERROR else "")
        message.status = status
        message.sources = sources or None
        message.skills = skills or None
        message.prompt_tokens = int(usage.get("prompt_tokens") or 0)
        message.completion_tokens = int(usage.get("completion_tokens") or 0)
        message.total_tokens = int(usage.get("total_tokens") or 0)
        message.latency_ms = round(latency_ms, 1)
        message.error_message = str(error_message)[:1000] if error_message else None
        message.extra = {
            "route": "rag" if sources else "direct",
            "knowledge_base_id": runtime.knowledge_base.id if runtime.knowledge_base else None,
            "skills": [item.get("name") for item in (skills or [])],
            "mcp_servers": [server.name for server in runtime.mcp_servers],
        }
        await self.session.flush()
        # 会话计数 +1（助手消息）
        runtime.conversation.message_count = (runtime.conversation.message_count or 0) + 1
        await self.session.commit()
        return to_message_out(message)

    async def _mark_skills_used(self, skills_used: list[dict[str, Any]]) -> None:
        """统计调用次数：技能与 MCP 服务分别累加（失败不影响主流程）。"""
        used = skills_used or []
        skill_ids = [
            int(item["id"]) for item in used if item.get("id") and item.get("source", "skill") != "mcp"
        ]
        mcp_ids = [int(item["id"]) for item in used if item.get("id") and item.get("source") == "mcp"]
        if not skill_ids and not mcp_ids:
            return
        try:
            if skill_ids:
                await SkillService(self.session).mark_used(skill_ids)
            if mcp_ids:
                await McpService(self.session).mark_used(sorted(set(mcp_ids)))
            await self.session.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("技能 / MCP 调用统计失败：%s", exc)
            await self.session.rollback()

    async def _touch_conversation(self, conversation: Conversation, *, used_tokens: int = 0) -> None:
        from datetime import datetime

        conversation.total_tokens = (conversation.total_tokens or 0) + max(0, used_tokens)
        conversation.last_message_at = datetime.now()
        await self.session.flush()
        await self.session.commit()

    async def _record_usage(
        self,
        runtime: ChatRuntime,
        answer: str,
        usage: dict[str, int],
        latency_ms: float,
        retrieved: int,
        *,
        success: bool = True,
    ) -> None:
        try:
            await self.usage.log(
                user_id=self.user_id,
                conversation_id=runtime.conversation.id,
                message_id=runtime.assistant_message.id if runtime.assistant_message else None,
                knowledge_base_id=runtime.knowledge_base.id if runtime.knowledge_base else None,
                provider=runtime.model.provider,
                model_name=runtime.model.model_name,
                source=UsageSource.CHAT,
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
                total_tokens=int(usage.get("total_tokens") or 0),
                retrieved_chunks=retrieved,
                latency_ms=latency_ms,
                success=success,
            )
            await self.session.commit()
        except Exception as exc:  # noqa: BLE001 - 统计失败不能影响聊天
            logger.warning("记录调用日志失败：%s", exc)
            await self.session.rollback()

    # ------------------------------------------------------------------ #
    async def stats_for_conversation(self, conversation_id: int) -> dict[str, Any]:
        conversation = await self.get_conversation(conversation_id)
        return {
            "message_count": await self.messages.count_by_conversation(conversation.id),
            "total_tokens": conversation.total_tokens,
            "model_id": conversation.model_id,
            "knowledge_base_id": conversation.knowledge_base_id,
        }

    async def knowledge_base_ready_stats(self, kb_id: int) -> dict[str, int]:
        """知识库就绪统计：用于前端提示「还有文档正在处理」。"""
        _, total = await self.documents.list_by_kb(kb_id, limit=1)
        processing = 0
        for status in (DocumentStatus.PENDING, DocumentStatus.PARSING, DocumentStatus.SPLITTING, DocumentStatus.EMBEDDING):
            _, count = await self.documents.list_by_kb(kb_id, status=status, limit=1)
            processing += count
        return {"documents": total, "processing": processing}


__all__ = ["ChatService", "ChatRuntime", "sse", "to_conversation_out", "to_message_out"]


# --------------------------------------------------------------------------- #
# 中断落库：独立任务 + 独立会话
# --------------------------------------------------------------------------- #
_background_persists: set[asyncio.Task] = set()


def schedule_stopped_persist(
    *,
    conversation_id: int,
    message_id: int,
    content: str,
    sources: list[dict[str, Any]],
    usage: dict[str, int],
    latency_ms: float,
    skills: list[dict[str, Any]] | None = None,
) -> None:
    """在独立任务中用独立会话保存「被中断」的助手消息。

    为什么不能直接用当前请求的会话？
      * 客户端断开时响应任务正在被销毁，响应协程中的任何 await 都会被取消，
        数据库操作随之回滚（消息状态会永远停留在 streaming）；
      * 因此这里创建全新任务 + 新会话，不受响应生命周期影响。
    """

    async def _run() -> None:
        from app.db.session import AsyncSessionLocal
        from app.models.message import Message

        try:
            async with AsyncSessionLocal() as session:
                message = await session.get(Message, message_id)
                if message is None:
                    return
                message.content = content or "（已停止生成，未产生内容）"
                message.status = MessageStatus.STOPPED
                message.sources = sources or None
                message.skills = skills or None
                message.prompt_tokens = int(usage.get("prompt_tokens") or 0)
                message.completion_tokens = int(usage.get("completion_tokens") or 0)
                message.total_tokens = int(usage.get("total_tokens") or 0)
                message.latency_ms = round(latency_ms, 1)

                conversation = await session.get(Conversation, conversation_id)
                if conversation is not None:
                    conversation.total_tokens = (conversation.total_tokens or 0) + int(
                        usage.get("total_tokens") or 0
                    )
                    conversation.last_message_at = datetime.now()

                await session.commit()
                logger.info(
                    "已保存被中断的回复 conversation=%s message=%s chars=%s",
                    conversation_id,
                    message_id,
                    len(content or ""),
                )
        except Exception as exc:  # noqa: BLE001 - 兜底，不能影响服务
            logger.warning("保存被中断的回复失败：%s", exc)

    task = asyncio.create_task(_run())
    _background_persists.add(task)
    task.add_done_callback(_background_persists.discard)
