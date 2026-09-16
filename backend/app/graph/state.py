"""LangGraph 工作流状态定义。

    START → 读取用户问题 → 判断是否使用知识库
                             ├─ 是 → RAG 检索 → LLM
                             └─ 否 → 直接 LLM
                                     ↓
                                  回答 → END

后续可扩展为：意图识别 → RAG → Tool Calling → Agent → LLM → 最终回答。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage

from app.rag.retriever import Retriever


class ChatState(TypedDict, total=False):
    """LangGraph 全局状态（对应开发文档 §13）。"""

    messages: list[BaseMessage]  # 历史消息（不含 System）
    question: str  # 当前问题
    context: list[dict[str, Any]]  # 检索到的分块
    context_text: str  # 拼接后的上下文文本
    knowledge_base_id: int | None
    knowledge_base_name: str | None
    model_id: int | None
    model_name: str | None
    system_prompt: str
    use_rag: bool
    route: str
    answer: str
    sources: list[dict[str, Any]]
    usage: dict[str, int]
    retrieval_failed: bool
    error: str | None
    notices: list[str]
    # ---- 技能（Tool Calling）----
    pending_tool_calls: list[dict[str, Any]]  # 本轮模型请求调用的工具
    tool_rounds: int  # 已经执行了几轮工具调用
    skills_used: list[dict[str, Any]]  # 已完成的技能调用记录（落库 + 前端展示）
    max_tool_rounds: int


class EventType:
    """SSE 事件类型。"""

    START = "start"
    META = "meta"
    ROUTE = "route"
    SOURCES = "sources"
    TOKEN = "token"
    SKILL = "skill"
    NOTICE = "notice"
    USAGE = "usage"
    ERROR = "error"
    DONE = "done"


@dataclass(slots=True)
class ChatDeps:
    """一次聊天请求的运行时依赖（通过闭包注入到各节点）。"""

    llm: BaseChatModel
    events: asyncio.Queue[dict[str, Any]]
    question: str
    system_prompt: str
    retriever: Retriever | None = None
    knowledge_base_id: int | None = None
    knowledge_base_name: str | None = None
    model_id: int | None = None
    model_name: str | None = None
    use_rag: bool = False
    extra_context: str | None = None
    notices: list[str] = field(default_factory=list)
    # 技能：可调用的工具 + 工具名到技能行（id/name/type）的映射
    tools: list[Any] = field(default_factory=list)
    skill_meta: dict[str, Any] = field(default_factory=dict)
    mcp_server_names: list[str] = field(default_factory=list)
    max_tool_rounds: int = 4

    def tool_names(self) -> list[str]:
        return [getattr(t, "name", "") for t in self.tools]

    async def emit(self, event_type: str, **payload: Any) -> None:
        await self.events.put({"type": event_type, **payload})


def initial_state(deps: ChatDeps, messages: list[BaseMessage]) -> ChatState:
    return ChatState(
        messages=messages,
        question=deps.question,
        knowledge_base_id=deps.knowledge_base_id,
        knowledge_base_name=deps.knowledge_base_name,
        model_id=deps.model_id,
        model_name=deps.model_name,
        system_prompt=deps.system_prompt,
        use_rag=bool(deps.use_rag and deps.retriever is not None),
        context=[],
        context_text="",
        sources=[],
        answer="",
        usage={},
        retrieval_failed=False,
        error=None,
        notices=list(deps.notices),
        pending_tool_calls=[],
        tool_rounds=0,
        skills_used=[],
        max_tool_rounds=deps.max_tool_rounds,
    )
