"""LangGraph 工作流编排。

工作流与 API 层完全解耦：`stream_graph()` 被 ChatService 调用，
一边执行工作流一边把事件推给上层（SSE），最后产出最终状态用于落库。

    START
      |
     route（判断是否使用知识库）
      |-- rag    -> retrieve --------
      `-- direct ---------------------
                                      v
                                   generate <-----------+
                                      |                 |
                         有 tool_calls > tools -----+
                        ` 无 tool_calls > finalize -> END

关于「停止生成 / 客户端断开」：
    生成器的 finally 中只会取消底层生成任务，**不做任何 yield**。
    因为在 GeneratorExit / CancelledError 传播期间再 yield 会破坏生成器协议。
    已生成内容的落库由 ChatService 用「独立任务 + 独立会话」完成（见 chat_service）。
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.core.logging import get_logger
from app.graph.nodes import make_nodes
from app.graph.state import ChatDeps, ChatState, EventType, initial_state

logger = get_logger(__name__)


def build_graph(deps: ChatDeps) -> Any:
    """为单次请求编译一个工作流（节点闭包持有请求级依赖）。"""
    nodes = make_nodes(deps)

    graph = StateGraph(ChatState)
    graph.add_node("route", nodes["route"])
    graph.add_node("retrieve", nodes["retrieve"])
    graph.add_node("generate", nodes["generate"])
    graph.add_node("tools", nodes["tools"])
    graph.add_node("finalize", nodes["finalize"])

    graph.add_edge(START, "route")
    graph.add_conditional_edges(
        "route",
        nodes["route_edge"],
        {"retrieve": "retrieve", "generate": "generate"},
    )
    graph.add_edge("retrieve", "generate")
    # 技能（Tool Calling）：模型要求调用工具时进入 tools 节点，执行完回到 generate
    graph.add_conditional_edges(
        "generate",
        nodes["generate_edge"],
        {"tools": "tools", "finalize": "finalize"},
    )
    graph.add_edge("tools", "generate")
    graph.add_edge("finalize", END)
    return graph.compile()


async def run_graph(deps: ChatDeps, messages: list[Any]) -> ChatState:
    """执行一次完整工作流（非流式场景 / 后台任务使用）。"""
    app = build_graph(deps)
    state = initial_state(deps, messages)
    return await app.ainvoke(state, {"recursion_limit": 40})


async def stream_graph(deps: ChatDeps, messages: list[Any]) -> AsyncIterator[dict[str, Any]]:
    """执行工作流并流式产出事件。

    * 工作流在后台任务中运行，主协程从事件队列消费 -> token 真正实时返回；
    * 结束（正常 / 被取消）都会产出 `done` 事件：正常时带上最终状态；
    * 生成器被关闭（客户端断开 / 点击停止生成）时会取消后台生成任务，
      并抛出 CancelledError 由上层处理落库。
    """
    task = asyncio.create_task(run_graph(deps, messages))
    try:
        while True:
            if task.done() and deps.events.empty():
                break
            try:
                event = await asyncio.wait_for(deps.events.get(), timeout=0.05)
            except asyncio.TimeoutError:
                continue
            yield event

        state = await task
        # 排空残留事件（例如最后一个 token）
        while not deps.events.empty():
            yield deps.events.get_nowait()
        yield {"type": EventType.DONE, "state": state}
    finally:
        # 正常结束、客户端断开、用户点击「停止生成」都会走到这里：
        # 只要生成任务还没结束就取消它，确保不再消耗模型额度。
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
            logger.info("聊天流已取消（用户停止生成 / 客户端断开）")
