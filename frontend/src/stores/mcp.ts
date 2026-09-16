/** MCP（Model Context Protocol）状态：管理列表 + 聊天可用服务 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { mcpApi } from '@/api/mcp'
import type {
  McpImportPayload,
  McpImportResult,
  McpServerItem,
  McpServerOption,
  McpServerPayload,
  McpTestResult,
  McpToolCallResult,
  McpTransportInfo,
} from '@/types'

export const useMcpStore = defineStore('mcp', () => {
  const servers = ref<McpServerItem[]>([])
  const available = ref<McpServerOption[]>([])
  const transports = ref<McpTransportInfo[]>([])
  const loading = ref(false)
  const loaded = ref(false)
  const transportsLoaded = ref(false)

  const enabledServers = computed(() => servers.value.filter((item) => item.enabled))
  const totalTools = computed(() => servers.value.reduce((sum, item) => sum + (item.tool_count || 0), 0))

  async function fetchServers(force = false) {
    if (loading.value) return servers.value
    if (loaded.value && !force && servers.value.length) return servers.value
    loading.value = true
    try {
      const data = await mcpApi.list({ page_size: 200 })
      servers.value = data.items
      loaded.value = true
      return servers.value
    } finally {
      loading.value = false
    }
  }

  async function fetchAvailable(force = false) {
    available.value = await mcpApi.available()
    return available.value
  }

  async function fetchTransports(force = false) {
    if (transportsLoaded.value && !force) return transports.value
    transports.value = await mcpApi.transports()
    transportsLoaded.value = true
    return transports.value
  }

  async function createServer(payload: McpServerPayload) {
    const created = await mcpApi.create(payload)
    await Promise.all([fetchServers(true), fetchAvailable(true)])
    return created
  }

  async function updateServer(id: number, payload: Partial<McpServerPayload>) {
    const updated = await mcpApi.update(id, payload)
    await Promise.all([fetchServers(true), fetchAvailable(true)])
    return updated
  }

  async function removeServer(id: number) {
    await mcpApi.remove(id)
    await Promise.all([fetchServers(true), fetchAvailable(true)])
  }

  async function toggleServer(id: number, enabled: boolean) {
    await mcpApi.toggle(id, enabled)
    await Promise.all([fetchServers(true), fetchAvailable(true)])
  }

  async function testServer(id: number): Promise<McpTestResult> {
    const result = await mcpApi.test(id)
    await Promise.all([fetchServers(true), fetchAvailable(true)])
    return result
  }

  async function importServers(payload: McpImportPayload) {
    const result = await mcpApi.importConfig(payload)
    await Promise.all([fetchServers(true), fetchAvailable(true)])
    return result
  }

  async function exportServers(includeSecrets = false) {
    return mcpApi.exportConfig(includeSecrets)
  }

  async function callTool(id: number, toolName: string, args: Record<string, unknown>) {
    return mcpApi.callTool(id, toolName, args) as Promise<McpToolCallResult>
  }

  function transportLabel(value?: string | null): string {
    if (!value) return '-'
    return transports.value.find((item) => item.value === value)?.label || value
  }

  return {
    servers,
    available,
    transports,
    loading,
    loaded,
    transportsLoaded,
    enabledServers,
    totalTools,
    fetchServers,
    fetchAvailable,
    fetchTransports,
    createServer,
    updateServer,
    removeServer,
    toggleServer,
    testServer,
    importServers,
    exportServers,
    callTool,
    transportLabel,
  }
})
