"""用于验证 MCP 功能的本地演示服务（stdio 传输）。

启动方式（由 MCP 管理功能自动拉起，也可手动测试）：
    python scripts/demo_mcp_server.py
"""

from __future__ import annotations

try:  # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:  # pragma: no cover - mcp < 2.0
    from mcp.server.fastmcp import FastMCP as _Server  # type: ignore

server = _Server("ai-chat-demo", instructions="AI Chat Assistant 的 MCP 演示服务")


@server.tool(description="把两个整数相加")
def add(a: int, b: int) -> str:
    return f"{a} + {b} = {a + b}"


@server.tool(description="回显一段文本")
def echo(text: str) -> str:
    return f"echo: {text}"


@server.tool(description="统计文本的字符数与词数")
def text_stats(text: str) -> str:
    words = len([w for w in text.replace(",", " ").split() if w])
    return f"字符数={len(text)} 词数={words}"


if __name__ == "__main__":
    server.run(transport="stdio")
