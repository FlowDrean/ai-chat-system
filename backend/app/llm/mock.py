"""本地 Mock 大模型。

用途：
1. 在没有配置任何真实 API Key 的情况下，也能完整跑通「前端 → SSE → LangGraph → 回答」链路；
2. 作为单元 / 集成测试的确定性 LLM；
3. 演示 Markdown 渲染（标题 / 列表 / 表格 / 引用 / 代码块）。

它实现了 LangChain 的 `BaseChatModel` 接口，因此可以像真实模型一样被
`astream()` / `ainvoke()` 使用，业务代码无需感知差异。
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator, Iterator
from typing import Any

from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

# RAG 上下文在 system message 中的分隔标记（与 rag/prompt 保持一致）
CONTEXT_MARKER = "【知识库内容】"


def _text_of(message: BaseMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):  # 多模态内容
        return " ".join(part.get("text", "") for part in content if isinstance(part, dict))
    return str(content)


def _split_chunks(text: str, size: int = 6) -> list[str]:
    """把回答切成小片段，模拟真实的逐 token 流式输出。"""
    return [text[i : i + size] for i in range(0, len(text), size)]



# --------------------------------------------------------------------------- #
# 技能（Tool Calling）支持
#
# 真实的 ChatOpenAI / ChatAnthropic 由 SDK 完成 function calling；
# 这里为本地 mock 模型实现一套确定性的触发规则，使「选技能  调用  回喂  作答」
# 整条链路在完全离线的情况下也能演示与自动化测试。
# --------------------------------------------------------------------------- #
_MATH_CHARS = set("0123456789+-*/%^(). \t")


def _extract_expression(text: str) -> str:
    """从自然语言里抽取数学表达式（支持以括号开头，例如 (88+12)/4*3）。"""
    best = ""
    current = ""
    for char in text:
        if char in _MATH_CHARS:
            current += char
        else:
            if len(current) > len(best):
                best = current
            current = ""
    if len(current) > len(best):
        best = current

    candidate = best.strip()
    while candidate and candidate[0] not in "0123456789+-.(":
        candidate = candidate[1:]
    while candidate and candidate[-1] not in "0123456789)":
        candidate = candidate[:-1]
    if (
        candidate
        and any(op in candidate for op in "+-*/%^")
        and any(ch.isdigit() for ch in candidate)
    ):
        return candidate
    return ""
_TOOL_HINTS: dict[str, tuple[str, ...]] = {
    "calculator": ("计算", "算一下", "等于", "多少", "calculate", "="),
    "current_time": ("时间", "几点", "日期", "星期", "今天", "现在"),
    "web_search": ("搜索", "搜一下", "查一下", "最新", "新闻", "search"),
    "web_fetch": ("抓取", "打开链接", "读取网页", "http"),
}


def _base_name(tool_name: str) -> str:
    """calculator_1 -> calculator；current-time_2 -> current_time"""
    parts = tool_name.rsplit("_", 1)
    base = parts[0] if len(parts) == 2 and parts[1].isdigit() else tool_name
    return base.replace("-", "_")


# 工具名 -> 展示名（mock 演示用）
_TOOL_LABELS = {
    "calculator": "计算器",
    "current_time": "当前时间",
    "web_search": "联网搜索",
    "web_fetch": "网页抓取",
}


def _tool_call_chunk(decision: dict[str, Any]) -> AIMessageChunk:
    """构造带 tool_call_chunks 的流式 chunk（合并后会得到 tool_calls）。"""
    import json as _json

    return AIMessageChunk(
        content="",
        tool_call_chunks=[
            {
                "name": decision["name"],
                "args": _json.dumps(decision["args"], ensure_ascii=False),
                "id": decision["id"],
                "index": 0,
                "type": "tool_call_chunk",
            }
        ],
    )




def _guess_args(tool: Any, text: str) -> dict[str, Any]:
    """根据工具的 args schema 粗略构造入参（仅 mock 演示用）。"""
    import re as _re

    args_schema = getattr(tool, "args", {}) or {}
    numbers = [int(n) for n in _re.findall(r"\d+", text or "")]
    number_index = 0
    result: dict[str, Any] = {}
    for name, spec in args_schema.items():
        if name == "_noop":
            continue
        json_type = (spec or {}).get("type")
        if json_type in ("integer", "number"):
            # 多个数字参数按出现顺序依次取值（123+456  a=123, b=456）
            result[name] = numbers[number_index] if number_index < len(numbers) else 1
            number_index += 1
        elif json_type == "boolean":
            result[name] = True
        else:
            result[name] = (text or "")[:200]
    return result

class MockChatModel(BaseChatModel):

    """离线可用的回显模型：会复述问题、引用检索到的上下文，并输出 Markdown 示例。"""

    model_name: str = "mock-chat"
    temperature: float = 0.7
    max_tokens: int = 2048
    chunk_size: int = 6
    stream_delay: float = 0.012

    # ------------------------------------------------------------------ #
    @property
    def _llm_type(self) -> str:
        return "mock-chat"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model_name": self.model_name, "temperature": self.temperature}

    # ------------------------------------------------------------------ #
    # 技能（工具调用）
    # ------------------------------------------------------------------ #
    def bind_tools(self, tools, **kwargs):  # noqa: ANN001, ANN003 - 兼容 LangChain 接口
        """把工具挂到模型上：真实模型由 SDK 处理，mock 用它做确定性触发。"""
        return self.bind(tools=list(tools), **kwargs)

    def _decide_tool_call(self, messages: list[BaseMessage], tools: list[Any]) -> dict[str, Any] | None:
        """根据用户问题决定调用哪个技能（模拟模型的 function calling 决策）。"""
        if not tools:
            return None
        # 已经执行过工具  本轮直接总结回答，避免死循环
        if any(message.type == "tool" for message in messages[-4:]):
            return None

        question = ""
        for message in reversed(messages):
            if message.type == "human":
                question = _text_of(message)
                break
        if not question.strip():
            return None

        by_base: dict[str, Any] = {}
        for tool in tools:
            by_base.setdefault(_base_name(getattr(tool, "name", "")), tool)

        def call(tool, args: dict[str, Any]) -> dict[str, Any]:
            return {"name": getattr(tool, "name", ""), "args": args, "id": f"call_{_base_name(tool.name)}"}

        # 1) 计算器：问题里出现数学表达式
        calc = by_base.get("calculator")
        if calc is not None:
            normalized = question.replace("\u00d7", "*").replace("\u00f7", "/")
            expression = _extract_expression(normalized)
            if expression and (
                any(hint in question for hint in _TOOL_HINTS["calculator"])
                or re.fullmatch(r"[\d\s.()+\-*/%^]+", expression.strip())
            ):
                return call(calc, {"expression": expression})

        # 2) 当前时间
        clock = by_base.get("current_time")
        if clock is not None and any(hint in question for hint in _TOOL_HINTS["current_time"]):
            return call(clock, {})

        # 3) 网页抓取：问题里带 URL
        fetch = by_base.get("web_fetch")
        if fetch is not None:
            url_match = re.search(r"https?://[^\s\u4e00-\u9fff，。；]+", question)
            if url_match:
                return call(fetch, {"url": url_match.group(0)})

        # 4) 联网搜索
        search = by_base.get("web_search")
        if search is not None and any(hint in question for hint in _TOOL_HINTS["web_search"]):
            return call(search, {"query": question.strip()[:200]})

        # 5) 点名调用：问题里出现 MCP 工具名，或「调用技能 xxx」
        explicit = re.search(r"(?:调用|使用)技能[：: ]?([\w\-\u4e00-\u9fff]+)", question)
        for base, tool in by_base.items():
            if base in {"calculator", "current_time", "web_search", "web_fetch"}:
                continue
            # 5.1 MCP 工具：直接点名（如 mcp_demo_add / demo_add / add）
            short = base.replace("mcp_", "")
            tail = base.rsplit("_", 1)[-1]  # 工具名最后一段（MCP 工具的真实名称）
            if base and (base in question or short in question or (len(tail) > 2 and tail in question)):
                return call(tool, _guess_args(tool, question))
            # 5.2 「调用技能 xxx」
            if explicit and base.endswith(explicit.group(1)):
                return call(tool, _guess_args(tool, question))
        if explicit:
            for base, tool in by_base.items():
                if base in {"calculator", "current_time", "web_search", "web_fetch"}:
                    continue
                return call(tool, _guess_args(tool, question))
        return None

    def _tool_call_message(self, decision: dict[str, Any]) -> AIMessage:
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": decision["name"],
                    "args": decision["args"],
                    "id": decision["id"],
                    "type": "tool_call",
                }
            ],
        )

    @staticmethod
    def _tool_context(messages: list[BaseMessage]) -> tuple[str, str] | None:
        """返回最近一次工具调用的 (工具展示名, 结果)。"""
        raw_name = ""
        for message in reversed(messages):
            calls = getattr(message, "tool_calls", None)
            if calls:
                raw_name = calls[0].get("name", "")
                break
        base = _base_name(raw_name)
        if base in _TOOL_LABELS:
            display = _TOOL_LABELS[base]
        elif base.startswith("mcp_"):
            display = f"MCP 工具（{base.replace('mcp_', '', 1)}）"
        else:
            display = base or "技能"
        for message in reversed(messages):
            if isinstance(message, ToolMessage) or message.type == "tool":
                return display, _text_of(message)
        return None

    # ------------------------------------------------------------------ #
    def _compose(self, messages: list[BaseMessage]) -> str:
        question = ""
        context_text = ""
        for message in reversed(messages):
            if message.type == "human":
                question = _text_of(message)
                break
        for message in messages:
            if message.type in ("system", "human") and CONTEXT_MARKER in _text_of(message):
                content = _text_of(message)
                context_text = content.split(CONTEXT_MARKER, 1)[1]
                break

        tool_context = self._tool_context(messages)
        lines: list[str] = []
        if tool_context is not None:
            tool_name, tool_output = tool_context
            lines.append("### 本地 Mock 模型回复（已调用技能）")
            lines.append("")
            lines.append(f"我调用了技能 **{tool_name or '未知技能'}**，它返回的结果是：")
            lines.append("")
            lines.append("```text")
            lines.append((tool_output or "").strip()[:1200])
            lines.append("```")
            lines.append("")
            lines.append(f"基于该结果回答你的问题：**{question.strip()[:160] or '（空消息）'}**")
            lines.append("")
            lines.append(
                "（以上结果来自技能实时调用，配置真实模型（如 DeepSeek / OpenAI）后，"
                "由模型自行决定是否调用技能并组织最终回答。）"
            )
            return "\n".join(lines)

        lines.append("### 本地 Mock 模型回复")
        lines.append("")
        lines.append(f"你问的是：**{question.strip()[:200] or '（空消息）'}**")
        lines.append("")
        lines.append("当前响应由内置的 `mock` 模型生成，用于在未配置真实 API Key 时验证系统链路。")
        lines.append("")

        if context_text.strip():
            snippets = [s.strip() for s in re.split(r"\n\[\d+\]", context_text) if s.strip()]
            lines.append("#### 我从知识库中检索到的内容")
            lines.append("")
            for idx, snippet in enumerate(snippets[:3], start=1):
                one_line = " ".join(snippet.split())
                lines.append(f"{idx}. {one_line[:160]}")
            lines.append("")
            lines.append("> 以上内容来自知识库检索，回答已优先基于这些资料。")
            lines.append("")
        else:
            lines.append("#### 说明")
            lines.append("")
            lines.append("本次对话未使用知识库检索（未选择知识库，或未检索到相关内容）。")
            lines.append("")

        lines.append("#### 支持的 Markdown 能力")
        lines.append("")
        lines.append("| 能力 | 说明 |")
        lines.append("| --- | --- |")
        lines.append("| 标题 / 列表 | 由 `marked` 渲染 |")
        lines.append("| 代码高亮 | 由 `highlight.js` 处理 |")
        lines.append("| 表格 / 引用 | 见上表与本段引用 |")
        lines.append("| XSS 过滤 | 经 `DOMPurify` 清洗 |")
        lines.append("")
        lines.append("```python")
        lines.append("from fastapi import FastAPI")
        lines.append("")
        lines.append('app = FastAPI(title="AI Chat Assistant")')
        lines.append("")
        lines.append('@app.get("/api/health")')
        lines.append("async def health() -> dict[str, str]:")
        lines.append('    return {"status": "ok"}')
        lines.append("```")
        lines.append("")
        lines.append("配置真实模型（模型管理 → 新增模型）后，把默认模型切换过去即可获得真实回答。")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,  # noqa: ARG002
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        decision = self._decide_tool_call(messages, kwargs.get("tools") or [])
        if decision is not None:
            return ChatResult(generations=[ChatGeneration(message=self._tool_call_message(decision))])
        text = self._compose(messages)
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=text))],
            llm_output={"model_name": self.model_name, "token_usage": self._approx_usage(messages, text)},
        )

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,  # noqa: ARG002
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        decision = self._decide_tool_call(messages, kwargs.get("tools") or [])
        if decision is not None:
            yield ChatGenerationChunk(message=_tool_call_chunk(decision))
            return
        text = self._compose(messages)
        for chunk in _split_chunks(text, self.chunk_size):
            if run_manager is not None:
                run_manager.on_llm_new_token(chunk)
            yield ChatGenerationChunk(message=AIMessageChunk(content=chunk))

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,  # noqa: ARG002
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        decision = self._decide_tool_call(messages, kwargs.get("tools") or [])
        if decision is not None:
            if run_manager is not None:
                await run_manager.on_llm_new_token("")
            yield ChatGenerationChunk(message=_tool_call_chunk(decision))
            return
        text = self._compose(messages)
        for chunk in _split_chunks(text, self.chunk_size):
            if self.stream_delay:
                await asyncio.sleep(self.stream_delay)
            if run_manager is not None:
                await run_manager.on_llm_new_token(chunk)
            yield ChatGenerationChunk(message=AIMessageChunk(content=chunk))

    # ------------------------------------------------------------------ #
    @staticmethod
    def _approx_usage(messages: list[BaseMessage], answer: str) -> dict[str, int]:
        prompt_chars = sum(len(_text_of(m)) for m in messages)
        prompt_tokens = max(1, prompt_chars // 2)
        completion_tokens = max(1, len(answer) // 2)
        return {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }
