<template>
  <AdminLayout>
    <div class="page-container">
      <div class="page-header">
        <div>
          <h1 class="page-title">MCP 管理</h1>
          <p class="page-subtitle">
            接入 Model Context Protocol 服务，把它们的工具交给 AI 调用。
            支持本地进程（stdio）与远程 SSE / Streamable HTTP 三种传输方式。
          </p>
        </div>
        <a-space>
          <a-input
            v-model:value="filters.keyword"
            placeholder="搜索名称 / 标识 / 地址"
            allow-clear
            style="width: 220px"
            @press-enter="load"
          >
            <template #prefix><SearchOutlined /></template>
          </a-input>
          <a-select
            v-model:value="filters.transport"
            :options="transportOptions"
            placeholder="全部传输方式"
            allow-clear
            style="width: 180px"
            @change="load"
          />
          <a-button @click="load">
            <template #icon><ReloadOutlined /></template>
          </a-button>
          <a-button @click="exportOpen = true">
            <template #icon><ExportOutlined /></template>
            导出配置
          </a-button>
          <a-button @click="importOpen = true">
            <template #icon><ImportOutlined /></template>
            导入配置
          </a-button>
          <a-button type="primary" @click="openCreate">
            <template #icon><PlusOutlined /></template>
            接入 MCP 服务
          </a-button>
        </a-space>
      </div>

      <a-row :gutter="14" class="mcp-page__stats">
        <a-col :xs="12" :md="6">
          <StatCard label="MCP 服务" :value="servers.length" :icon="ApiOutlined" />
        </a-col>
        <a-col :xs="12" :md="6">
          <StatCard label="已启用" :value="servers.filter((s) => s.enabled).length" :icon="LinkOutlined" />
        </a-col>
        <a-col :xs="12" :md="6">
          <StatCard label="可用工具" :value="store.totalTools" :icon="ToolOutlined" />
        </a-col>
        <a-col :xs="12" :md="6">
          <StatCard
            label="连接正常"
            :value="servers.filter((s) => s.status === 'ok').length"
            :icon="CheckCircleOutlined"
          />
        </a-col>
      </a-row>

      <a-card :bordered="true" size="small">
        <LoadingView v-if="loading && !servers.length" text="加载 MCP 服务中…" />

        <EmptyState
          v-else-if="!servers.length"
          :icon="ApiOutlined"
          title="还没有接入 MCP 服务"
          description="接入后，MCP 服务暴露的工具会出现在聊天的「MCP」选择器里，由模型按需调用。"
        >
          <a-button type="primary" @click="openCreate">接入 MCP 服务</a-button>
        </EmptyState>

        <a-table v-else :data-source="servers" :columns="columns" row-key="id" :pagination="false" size="middle">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'name'">
              <div class="mcp-name">
                <span class="mcp-name__icon"><ApiOutlined /></span>
                <div class="mcp-name__info">
                  <span class="text-ellipsis">{{ record.name }}</span>
                  <small class="mono text-secondary">{{ record.slug }}</small>
                </div>
              </div>
            </template>

            <template v-else-if="column.key === 'transport'">
              <a-tag class="tag-mono">{{ record.transport_label }}</a-tag>
            </template>

            <template v-else-if="column.key === 'target'">
              <span class="mono mcp-target text-ellipsis" :title="target(record)">{{ target(record) }}</span>
            </template>

            <template v-else-if="column.key === 'status'">
              <a-tooltip :title="record.status_message || ''">
                <a-badge
                  :status="record.status === 'ok' ? 'success' : record.status === 'error' ? 'error' : 'default'"
                  :text="record.status === 'ok' ? '正常' : record.status === 'error' ? '异常' : '未测试'"
                />
              </a-tooltip>
            </template>

            <template v-else-if="column.key === 'tool_count'">
              <a-button type="link" size="small" :disabled="!record.tool_count" @click="openTools(record)">
                {{ record.tool_count }} 个工具
              </a-button>
            </template>

            <template v-else-if="column.key === 'enabled'">
              <a-switch
                :checked="record.enabled"
                size="small"
                @change="(checked: unknown) => handleToggle(record, Boolean(checked))"
              />
            </template>

            <template v-else-if="column.key === 'usage_count'">
              {{ record.usage_count || 0 }}
            </template>

            <template v-else-if="column.key === 'last_connected_at'">
              {{ record.last_connected_at ? formatDateTime(record.last_connected_at) : '未连接' }}
            </template>

            <template v-else-if="column.key === 'action'">
              <a-space :size="2">
                <a-tooltip title="测试连接 / 刷新工具">
                  <a-button size="small" type="text" :loading="testingId === record.id" @click="handleTest(record)">
                    <template #icon><ApiOutlined /></template>
                  </a-button>
                </a-tooltip>
                <a-tooltip title="配置">
                  <a-button size="small" type="text" @click="openEdit(record)">
                    <template #icon><SettingOutlined /></template>
                  </a-button>
                </a-tooltip>
                <a-popconfirm title="删除该 MCP 服务？" ok-text="删除" cancel-text="取消" @confirm="handleDelete(record)">
                  <a-button size="small" type="text" danger>
                    <template #icon><DeleteOutlined /></template>
                  </a-button>
                </a-popconfirm>
              </a-space>
            </template>
          </template>
        </a-table>
      </a-card>

      <a-card :bordered="true" size="small" title="支持的传输方式" class="mcp-page__guide">
        <a-row :gutter="16">
          <a-col v-for="item in store.transports" :key="item.value" :xs="24" :md="8">
            <div class="mcp-transport">
              <div class="mcp-transport__head">
                <a-tag class="tag-mono">{{ item.label }}</a-tag>
              </div>
              <p class="mcp-transport__desc">{{ item.description }}</p>
            </div>
          </a-col>
        </a-row>
        <a-alert
          type="info"
          show-icon
          class="mcp-page__tip"
          message="工具是「连接时发现、缓存到本地」的"
          description="点「测试连接」会拉取 tools/list 并缓存工具的 JSON Schema，聊天时直接用缓存构建工具，无需每次握手；服务端工具变更后重新测试即可刷新。也可以直接粘贴 claude_desktop_config.json 里的 mcpServers 配置一键导入（支持 command/args/env 与 url/headers 两种写法）。"
        />
      </a-card>
    </div>

    <McpConfigForm v-model:open="formOpen" :current="editing" @saved="handleSaved" />
    <McpImportModal v-model:open="importOpen" @imported="handleImported" />
    <McpExportModal v-model:open="exportOpen" />

    <!-- 工具清单 -->
    <a-drawer v-model:open="toolsOpen" :title="`${toolsTarget?.name || ''} · 工具清单`" placement="right" :width="620">
      <EmptyState
        v-if="!toolsTarget?.tools?.length"
        :icon="ToolOutlined"
        title="暂无工具缓存"
        description="点「测试连接」即可从 MCP 服务发现工具。"
      />
      <div v-else class="mcp-page__tools">
        <div v-for="tool in toolsTarget.tools" :key="tool.name" class="mcp-tool-card">
          <div class="mcp-tool-card__head">
            <span class="mono">{{ tool.name }}</span>
          </div>
          <p class="mcp-tool-card__desc">{{ tool.description || '（无描述）' }}</p>
          <pre class="mcp-tool-card__schema">{{ JSON.stringify(tool.input_schema, null, 2) }}</pre>
        </div>
      </div>
    </a-drawer>
  </AdminLayout>
</template>

<script setup lang="ts">
/** MCP 管理页：服务列表 / 接入 / 连接测试 / 工具清单 / 启停 / 删除 */
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import type { TableColumnsType } from 'ant-design-vue'
import {
  ApiOutlined,
  CheckCircleOutlined,
  DeleteOutlined,
  ExportOutlined,
  ImportOutlined,
  LinkOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  SettingOutlined,
  ToolOutlined,
} from '@ant-design/icons-vue'

import EmptyState from '@/components/common/EmptyState.vue'
import LoadingView from '@/components/common/LoadingView.vue'
import StatCard from '@/components/common/StatCard.vue'
import McpConfigForm from '@/components/mcp/McpConfigForm.vue'
import McpExportModal from '@/components/mcp/McpExportModal.vue'
import McpImportModal from '@/components/mcp/McpImportModal.vue'
import AdminLayout from '@/layouts/AdminLayout.vue'
import { useMcpStore } from '@/stores/mcp'
import type { McpServerItem } from '@/types'
import { formatDateTime } from '@/utils/format'

const store = useMcpStore()

const loading = ref(false)
const formOpen = ref(false)
const editing = ref<McpServerItem | null>(null)
const testingId = ref<number | null>(null)
const toolsOpen = ref(false)
const importOpen = ref(false)
const exportOpen = ref(false)
const toolsTarget = ref<McpServerItem | null>(null)
const filters = reactive<{ keyword?: string; transport?: string }>({ keyword: undefined, transport: undefined })

const servers = computed(() => store.servers)
const transportOptions = computed(() => store.transports.map((item) => ({ value: item.value, label: item.label })))

const columns: TableColumnsType = [
  { title: '服务', key: 'name', width: 200 },
  { title: '传输方式', key: 'transport', width: 150 },
  { title: '目标', key: 'target', ellipsis: true },
  { title: '状态', key: 'status', width: 110 },
  { title: '工具', key: 'tool_count', width: 110 },
  { title: '启用', key: 'enabled', width: 80 },
  { title: '调用次数', key: 'usage_count', width: 100 },
  { title: '最近连接', key: 'last_connected_at', width: 160 },
  { title: '操作', key: 'action', width: 150, fixed: 'right' },
]

function target(record: McpServerItem): string {
  if (record.transport === 'stdio') {
    const args = (record.args || []).join(' ')
    return `${record.command || ''} ${args}`.trim() || '-'
  }
  return record.url || '-'
}

async function load() {
  loading.value = true
  try {
    await store.fetchServers(true)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  formOpen.value = true
}

function openEdit(record: McpServerItem) {
  editing.value = record
  formOpen.value = true
}

function openTools(record: McpServerItem) {
  toolsTarget.value = record
  toolsOpen.value = true
}

function handleImported() {
  load()
}

async function handleSaved(server?: McpServerItem) {
  await load()
  if (server && !server.tool_count) {
    message.info('服务已保存，建议点「测试连接」验证并发现工具')
  }
}

async function handleTest(record: McpServerItem) {
  testingId.value = record.id
  try {
    const result = await store.testServer(record.id)
    if (result.success) {
      message.success(`连接成功，发现 ${result.tool_count} 个工具（${result.latency_ms}ms）`)
      toolsTarget.value = { ...record, tools: result.tools, tool_count: result.tool_count }
    } else {
      message.error(result.message)
    }
  } catch {
    /* 统一错误提示已由 axios 拦截器处理 */
  } finally {
    testingId.value = null
  }
}

async function handleToggle(record: McpServerItem, enabled: boolean) {
  await store.toggleServer(record.id, enabled)
  message.success(enabled ? '已启用' : '已禁用')
}

async function handleDelete(record: McpServerItem) {
  await store.removeServer(record.id)
  message.success('MCP 服务已删除')
  await load()
}

onMounted(async () => {
  await Promise.all([store.fetchTransports(), load()])
})
</script>

<style scoped>
.mcp-page__stats {
  margin-bottom: 16px;
}

.mcp-name {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.mcp-name__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: var(--brand-soft);
  color: var(--brand);
  flex-shrink: 0;
}

.mcp-name__info {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
  min-width: 0;
}

.mcp-name__info small {
  font-size: 11px;
}

.mcp-target {
  font-size: 12px;
  color: var(--text-secondary);
  max-width: 320px;
  display: inline-block;
}

.mcp-page__guide {
  margin: 16px 0 24px;
}

.mcp-transport {
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  height: 100%;
}

.mcp-transport__desc {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
}

.mcp-page__tip {
  margin-top: 16px;
}

.mcp-page__tools {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mcp-tool-card {
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
}

.mcp-tool-card__head {
  font-size: 13px;
  font-weight: 600;
}

.mcp-tool-card__desc {
  margin: 4px 0 8px;
  font-size: 12px;
  color: var(--text-secondary);
}

.mcp-tool-card__schema {
  margin: 0;
  max-height: 200px;
  overflow: auto;
  padding: 8px 10px;
  background: var(--bg-sunken);
  border-radius: var(--radius-sm);
  font-size: 11px;
  line-height: 1.6;
}
</style>
