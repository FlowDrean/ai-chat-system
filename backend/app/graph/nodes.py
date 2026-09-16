"""LangGraph 各节点实现。

节点通过闭包持有 `ChatDeps`，因此可以自由使用数据库 / 检索器 / 技能 / 事件队列，
而工作流本身与 API 层完全解耦（见开发文档 §49.11）。

技能（Tool Calling）流程：

    generate ──(模型返回 tool_calls)──> tools ──> generate ──> ... ──> finalize
        └────(普通回答)────────────────────────────────────────────> finalize
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage

from app.core.exceptions import AppError, RetrievalError
from app.core.logging import get_logger
from app.graph.state import ChatDeps, ChatState
from app.llm.factory import _friendly_error
from app.rag.prompts import CONTEXT_MARKER, RETRIEVAL_EMPTY_HINT
from app.rag.retriever import build_context, to_sources

logger = get_logger(__name__)

MAX_TOOL_OUTPUT_CHARS = 4000


def make_nodes(deps: ChatDeps) -> dict[str, Callable[[ChatState], Any]]:
    """创建本次请求使用的节点集合。"""

    # ------------------------------------------------------------------ #
    async def route_node(state: ChatState) -> ChatState:
        """判断是否需要走 RAG（是否选择了知识库 / 是否检索到内容）。"""
        use_rag = bool(state.get("use_rag") and deps.retriever is not None)
        await deps.emit(
            "route",
            use_rag=use_rag,
            knowledge_base_id=state.get("knowledge_base_id"),
            knowledge_base_name=state.get("knowledge_base_name"),
            skills=[m.get("name") for m in deps.skill_meta.values() if m.get("source", "skill") != "mcp"],
            mcp_servers=list(deps.mcp_server_names),
        )
        return ChatState(route="rag" if use_rag else "direct", use_rag=use_rag)

    def route_edge(state: ChatState) -> str:
        return "retrieve" if state.get("use_rag") else "generate"

    # ------------------------------------------------------------------ #
    async def retrieve_node(state: ChatState) -> ChatState:
        """RAG 检索：失败时降级为普通对话，不让整个请求失败（见开发文档 §35）。"""
        assert deps.retriever is not None
        question = state.get("question", "")
        try:
            chunks = await deps.retriever.retrieve(question)
        except (RetrievalError, AppError) as exc:
            logger.warning("知识库检索失败，降级为普通对话：%s", exc)
            notice = "知识库检索失败，已自动降级为普通对话"
            await deps.emit("notice", level="warning", message=notice)
            return ChatState(use_rag=False, retrieval_failed=True, notices=[*state.get("notices", []), notice])

        if not chunks:
            notice = "知识库中没有检索到相关内容，已基于通用知识回答"
            await deps.emit("notice", level="info", message=notice)
            return ChatState(
                use_rag=False,
                context=[],
                context_text="",
                sources=[],
                notices=[*state.get("notices", []), notice],
            )

        context_text = build_context(chunks)
        sources = to_sources(chunks)
        await deps.emit("sources", sources=sources, count=len(sources))
        return ChatState(
            context=[chunk.to_source() for chunk in chunks],
            context_text=context_text,
            sources=sources,
            use_rag=True,
        )

    # ------------------------------------------------------------------ #
    async def generate_node(state: ChatState) -> ChatState:
        """调用 LLM 生成回答。

        * 绑定了技能时用 `astream` 累积出完整 AIMessage，若模型返回 `tool_calls`
          则交给 tools 节点执行（本轮不产出正文）；
        * 未调用工具时把 token 实时推送出去（真流式）。
        """
        messages = _build_messages(state)
        llm = _bind_tools(deps)

        answer_parts: list[str] = []
        usage: dict[str, int] = {}
        chunks: list[Any] = []

        try:
            async for chunk in llm.astream(messages):
                chunks.append(chunk)
                text = _chunk_text(chunk)
                if text:
                    # 真流式：token 到达即推送（工具调用轮次的 content 通常为空，
                    # 因此不影响下面的 tool_calls 决策）
                    answer_parts.append(text)
                    await deps.emit("token", content=text)
                chunk_usage = getattr(chunk, "usage_metadata", None)
                if chunk_usage:
                    usage = {
                        "prompt_tokens": int(chunk_usage.get("input_tokens") or 0),
                        "completion_tokens": int(chunk_usage.get("output_tokens") or 0),
                        "total_tokens": int(chunk_usage.get("total_tokens") or 0),
                    }
        except Exception as exc:  # noqa: BLE001
            message = _friendly_error(exc)
            logger.warning("LLM 生成失败：%s", message)
            partial = "".join(answer_parts)
            await deps.emit("error", code=50101, message=message, partial=partial)
            return ChatState(answer=partial, error=message, usage=usage)

        merged = _merge_chunks(chunks)
        tool_calls = [call for call in (getattr(merged, "tool_calls", None) or []) if call.get("name")]

        if tool_calls:
            # 有工具要调用：本轮不产出正文，把消息与调用请求交给 tools 节点
            await deps.emit(
                "skill",
                phase="planned",
                calls=[
                    {"name": call.get("name"), "arguments": call.get("args") or {}} for call in tool_calls
                ],
            )
            return ChatState(
                pending_tool_calls=tool_calls,
                ai_message=merged,
                usage=usage or state.get("usage") or {},
                error=None,
            )

        answer = "".join(answer_parts)
        if not usage:
            usage = _estimate_usage(messages, answer)
        return ChatState(
            answer=answer,
            usage=usage,
            error=None,
            pending_tool_calls=[],
            ai_message=None,
        )

    def generate_edge(state: ChatState) -> str:
        pending = state.get("pending_tool_calls") or []
        rounds = int(state.get("tool_rounds") or 0)
        max_rounds = int(state.get("max_tool_rounds") or deps.max_tool_rounds)
        if pending and rounds < max_rounds:
            return "tools"
        return "finalize"

    # ------------------------------------------------------------------ #
    async def tools_node(state: ChatState) -> ChatState:
        """执行模型请求的技能调用，并把结果以 ToolMessage 回喂给模型。"""
        calls = state.get("pending_tool_calls") or []
        raw_ai_message = state.get("ai_message")
        base_messages = list(state.get("messages") or [])
        new_messages: list[BaseMessage] = []
        if calls:
            # 关键：流式累积出来的是 AIMessageChunk，直接回喂给 OpenAI 兼容接口会报
            # 「Messages with role 'tool' must be a response to a preceding message with 'tool_calls'」，
            # 因此这里重建一条规范的 AIMessage（显式带 tool_calls）。
            new_messages.append(
                AIMessage(
                    content=_chunk_text(raw_ai_message) if raw_ai_message is not None else "",
                    tool_calls=[
                        {
                            "name": str(call.get("name") or ""),
                            "args": call.get("args") or {},
                            "id": str(call.get("id") or f"call_{index}"),
                            "type": "tool_call",
                        }
                        for index, call in enumerate(calls)
                    ],
                )
            )

        records: list[dict[str, Any]] = list(state.get("skills_used") or [])
        tools_by_name = {getattr(tool, "name", ""): tool for tool in deps.tools}

        for index, call in enumerate(calls):
            tool_name = str(call.get("name") or "")
            arguments = call.get("args") or {}
            if not isinstance(arguments, dict):
                arguments = {"input": arguments}
            call_id = str(call.get("id") or f"call_{index}")
            meta = deps.skill_meta.get(tool_name) or {}
            display_name = str(meta.get("name") or tool_name)

            await deps.emit(
                "skill",
                phase="call",
                call_id=call_id,
                name=display_name,
                tool_name=tool_name,
                skill_type=meta.get("type"),
                source=meta.get("source", "skill"),
                server=meta.get("server"),
                arguments=arguments,
            )

            started = time.perf_counter()
            tool = tools_by_name.get(tool_name)
            if tool is None:
                output = f"[技能不可用] 未找到工具 {tool_name}（可能已被禁用）"
                status = "error"
            else:
                try:
                    raw = await tool.ainvoke(arguments)
                    output = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
                    status = "error" if output.startswith("[技能执行失败]") else "ok"
                except Exception as exc:  # noqa: BLE001
                    logger.warning("技能执行异常 tool=%s: %s", tool_name, exc)
                    output = f"[技能执行失败] {exc}"
                    status = "error"
            latency = (time.perf_counter() - started) * 1000

            trimmed = output[:MAX_TOOL_OUTPUT_CHARS]
            record = {
                "id": meta.get("id"),
                "name": display_name,
                "type": meta.get("type"),
                "source": meta.get("source", "skill"),
                "server": meta.get("server"),
                "tool_name": tool_name,
                "status": status,
                "arguments": arguments,
                "output": trimmed,
                "latency_ms": round(latency, 1),
            }
            records.append(record)

            await deps.emit(
                "skill",
                phase="result",
                call_id=call_id,
                name=display_name,
                tool_name=tool_name,
                skill_type=meta.get("type"),
                source=meta.get("source", "skill"),
                server=meta.get("server"),
                status=status,
                arguments=arguments,
                output=trimmed,
                latency_ms=round(latency, 1),
            )
            new_messages.append(ToolMessage(content=trimmed, tool_call_id=call_id, name=tool_name))

        return ChatState(
            messages=[*base_messages, *new_messages],
            pending_tool_calls=[],
            ai_message=None,
            tool_rounds=int(state.get("tool_rounds") or 0) + 1,
            skills_used=records,
        )

    # ------------------------------------------------------------------ #
    async def finalize_node(state: ChatState) -> ChatState:
        """收尾：记录本次路由与技能调用情况，便于前端 / 日志追踪。"""
        logger.info(
            "回答完成 route=%s rag=%s sources=%s skills=%s chars=%s",
            state.get("route"),
            state.get("use_rag"),
            len(state.get("sources") or []),
            len(state.get("skills_used") or []),
            len(state.get("answer") or ""),
        )
        return ChatState()

    return {
        "route": route_node,
        "retrieve": retrieve_node,
        "generate": generate_node,
        "tools": tools_node,
        "finalize": finalize_node,
        "route_edge": route_edge,
        "generate_edge": generate_edge,
    }


# --------------------------------------------------------------------------- #
# 辅助函数
# --------------------------------------------------------------------------- #
def _bind_tools(deps: ChatDeps):  # noqa: ANN202
    """把技能绑定到模型；不支持 function calling 的模型自动降级为普通对话。"""
    if not deps.tools:
        return deps.llm
    try:
        bound = deps.llm.bind_tools(deps.tools)
        logger.info("已绑定技能工具：%s", [getattr(t, "name", "") for t in deps.tools])
        return bound
    except Exception as exc:  # noqa: BLE001
        logger.info("当前模型不支持工具调用，已忽略已选技能：%s", exc)
        deps.notices.append("当前模型不支持技能调用，已按普通对话回答")
        return deps.llm


def _merge_chunks(chunks: list[Any]) -> Any:
    """把流式 chunk 合并成一个完整消息（用于读取 tool_calls）。"""
    if not chunks:
        return AIMessage(content="")
    merged = chunks[0]
    for chunk in chunks[1:]:
        try:
            merged = merged + chunk
        except Exception:  # noqa: BLE001 - 个别模型的 chunk 不支持相加
            return chunks[-1]
    return merged


def _build_messages(state: ChatState) -> list[BaseMessage]:
    """组装最终发给 LLM 的消息：System（含 RAG 上下文） + 历史/工具消息。"""
    system_prompt = (state.get("system_prompt") or "").strip()
    context_text = (state.get("context_text") or "").strip()

    if state.get("use_rag") and context_text:
        if "{context}" in system_prompt or "{知识库内容}" in system_prompt:
            system_content = system_prompt.replace("{context}", context_text)
        else:
            system_content = f"{system_prompt}\n\n{CONTEXT_MARKER}\n{context_text}"
    else:
        system_content = system_prompt
        if state.get("retrieval_failed") or state.get("knowledge_base_id"):
            system_content = f"{system_content}\n\n{RETRIEVAL_EMPTY_HINT}".strip()

    messages: list[BaseMessage] = []
    if system_content.strip():
        messages.append(SystemMessage(content=system_content))
    messages.extend(state.get("messages") or [])
    return messages


def _chunk_text(chunk: Any) -> str:
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                parts.append(str(part.get("text", "")))
            elif isinstance(part, str):
                parts.append(part)
        return "".join(parts)
    return str(content) if content else ""


def _estimate_usage(messages: list[BaseMessage], answer: str) -> dict[str, int]:
    """供应商未返回 usage 时的估算（真实用量以供应商返回为准）。"""
    from app.rag.splitter import estimate_tokens

    prompt_tokens = max(1, sum(estimate_tokens(_chunk_text(m)) for m in messages))
    completion_tokens = max(1, estimate_tokens(answer))
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }
