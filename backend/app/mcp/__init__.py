"""MCP（Model Context Protocol）支持。

    app/mcp/client.py   连接 MCP Server（stdio / sse / http） 发现工具  调用工具
    app/mcp/bridge.py   把 MCP 工具桥接成 LangChain Tool，复用现有 tool-calling 链路

上层（Service / API / LangGraph）只依赖这两个模块，不感知 MCP 协议细节；
mcp 1.x 与 2.x 的差异也收敛在 client.py 内部。
"""

from app.mcp.bridge import build_mcp_tools, json_schema_to_model, server_snapshot, tool_name_for
from app.mcp.client import McpCallResult, McpError, McpToolInfo, call_tool, list_tools

__all__ = [
    "McpCallResult",
    "McpError",
    "McpToolInfo",
    "build_mcp_tools",
    "call_tool",
    "json_schema_to_model",
    "list_tools",
    "server_snapshot",
    "tool_name_for",
]
