/** MCP（Model Context Protocol）接口 */
import { request } from './request'
import type {
  McpExportResult,
  McpImportPayload,
  McpImportResult,
  McpServerItem,
  McpServerOption,
  McpServerPayload,
  McpTestResult,
  McpTool,
  McpToolCallResult,
  McpTransportInfo,
  PageData,
  PageQuery,
} from '@/types'

export interface McpQuery extends PageQuery {
  keyword?: string
  transport?: string
  enabled?: boolean
}

export const mcpApi = {
  /** 管理列表（管理员） */
  list(params: McpQuery = {}) {
    return request.get<PageData<McpServerItem>>('/mcp/servers', { params: { page_size: 100, ...params } })
  },
  /** 聊天可用（任意登录用户） */
  available() {
    return request.get<McpServerOption[]>('/mcp/available')
  },
  transports() {
    return request.get<McpTransportInfo[]>('/mcp/transports')
  },
  get(id: number) {
    return request.get<McpServerItem>(`/mcp/servers/${id}`)
  },
  create(payload: McpServerPayload) {
    return request.post<McpServerItem>('/mcp/servers', payload)
  },
  update(id: number, payload: Partial<McpServerPayload>) {
    return request.put<McpServerItem>(`/mcp/servers/${id}`, payload)
  },
  remove(id: number) {
    return request.delete<{ message: string }>(`/mcp/servers/${id}`)
  },
  toggle(id: number, enabled: boolean) {
    return request.patch<McpServerItem>(`/mcp/servers/${id}/enabled`, undefined, { params: { enabled } })
  },
  /** 连接测试 + 发现工具 */
  test(id: number) {
    return request.post<McpTestResult>(`/mcp/servers/${id}/test`, undefined, { timeout: 180_000 })
  },
  tools(id: number) {
    return request.get<McpTool[]>(`/mcp/servers/${id}/tools`)
  },
  /** 导入 mcpServers 配置（Claude Desktop / Cursor 格式） */
  importConfig(payload: McpImportPayload) {
    return request.post<McpImportResult>('/mcp/import', payload, { timeout: 600_000 })
  },
  /** 导出 mcpServers 配置 */
  exportConfig(includeSecrets = false) {
    return request.get<McpExportResult>('/mcp/export', { params: { include_secrets: includeSecrets } })
  },
  /** 调试调用某个工具 */
  callTool(id: number, toolName: string, args: Record<string, unknown> = {}) {
    return request.post<McpToolCallResult>(
      `/mcp/servers/${id}/call-tool`,
      { tool_name: toolName, arguments: args },
      { timeout: 180_000 },
    )
  },
}
