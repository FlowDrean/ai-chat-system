<template>
  <a-modal
    :open="open"
    title="导入 MCP 配置"
    :width="760"
    :confirm-loading="importing"
    ok-text="开始导入"
    cancel-text="取消"
    destroy-on-close
    @ok="submit"
    @cancel="close"
  >
    <a-alert
      type="info"
      show-icon
      class="mcp-import__tip"
      message="支持 Claude Desktop / Cursor / VS Code 的 mcpServers 配置"
      description="可直接粘贴 JSON，或选择 claude_desktop_config.json 之类的配置文件；支持 stdio（command/args/env）与远程（url/headers/type）两种写法。"
    />

    <div class="mcp-import__toolbar">
      <a-upload :show-upload-list="false" accept=".json,application/json" :before-upload="handleFile">
        <a-button size="small">
          <template #icon><UploadOutlined /></template>
          选择 JSON 文件
        </a-button>
      </a-upload>
      <a-button size="small" @click="fillExample">填入示例（高德地图）</a-button>
      <a-button size="small" :disabled="!payload" @click="payload = ''">清空</a-button>
      <span class="mcp-import__count text-secondary">
        {{ preview.length ? `识别到 ${preview.length} 个服务` : '尚未识别到服务' }}
      </span>
    </div>

    <a-textarea
      v-model:value="payload"
      class="mcp-import__editor"
      :rows="12"
      placeholder='{
  "mcpServers": {
    "amap-maps": {
      "command": "npx",
      "args": ["-y", "@amap/amap-maps-mcp-server"],
      "env": { "AMAP_MAPS_API_KEY": "你的高德 Key" }
    }
  }
}'
    />

    <a-table
      v-if="preview.length"
      class="mcp-import__preview"
      :data-source="preview"
      :columns="previewColumns"
      :pagination="false"
      size="small"
      row-key="name"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'name'">
          <span class="mono">{{ record.name }}</span>
        </template>
        <template v-else-if="column.key === 'transport'">
          <a-tag class="tag-mono">{{ record.transport }}</a-tag>
        </template>
        <template v-else-if="column.key === 'target'">
          <span class="mono text-secondary">{{ record.target }}</span>
        </template>
        <template v-else-if="column.key === 'secret'">
          <a-tag v-if="record.hasSecret" class="tag-mono is-muted">含密钥</a-tag>
        </template>
      </template>
    </a-table>

    <a-form layout="vertical" class="mcp-import__options">
      <a-row :gutter="16">
        <a-col :xs="24" :md="8">
          <a-form-item label="名称冲突处理">
            <a-select v-model:value="strategy" :options="strategyOptions" />
          </a-form-item>
        </a-col>
        <a-col :xs="12" :md="8">
          <a-form-item label="导入后自动测试连接">
            <a-switch v-model:checked="autoTest" />
          </a-form-item>
        </a-col>
        <a-col :xs="12" :md="8">
          <a-form-item label="允许用户在聊天中选择">
            <a-switch v-model:checked="visibleToUsers" />
          </a-form-item>
        </a-col>
      </a-row>
    </a-form>

    <a-alert
      v-if="autoTest"
      type="warning"
      show-icon
      class="mcp-import__tip"
      message="自动测试会真实启动 / 连接这些服务"
      description="stdio 服务（如 npx 包）首次运行需要下载依赖，可能需要几十秒；npx / npm / uvx 在 Windows 下会自动用 cmd /c 包装执行。"
    />

    <!-- 导入结果 -->
    <template v-if="result">
      <a-divider orientation="left" class="mcp-import__divider">
        导入结果（新增 {{ result.created }} / 覆盖 {{ result.updated }} / 跳过 {{ result.skipped }} / 失败 {{ result.failed }}）
      </a-divider>
      <a-alert v-for="(warning, index) in result.warnings" :key="index" type="warning" show-icon :message="warning" class="mcp-import__tip" />
      <div class="mcp-import__results">
        <div v-for="item in result.items" :key="item.slug + item.action" class="mcp-result">
          <div class="mcp-result__head">
            <a-tag class="tag-mono" :class="{ 'is-strong': item.action === 'created', 'is-muted': item.action === 'skipped', 'is-error': item.action === 'failed' }">
              {{ actionLabel(item.action) }}
            </a-tag>
            <span class="mcp-result__name">{{ item.name }}</span>
            <span class="mono text-secondary mcp-result__slug">{{ item.slug }}</span>
            <a-tag v-if="item.tool_count" class="tag-mono mcp-result__tools">{{ item.tool_count }} 个工具</a-tag>
          </div>
          <p class="mcp-result__message">{{ item.message }}</p>
          <div v-if="item.tools?.length" class="mcp-result__tool-list">
            <code v-for="tool in item.tools" :key="tool.name">{{ tool.name }}</code>
          </div>
        </div>
      </div>
    </template>
  </a-modal>
</template>

<script setup lang="ts">
/**
 * MCP 配置导入弹窗
 * 支持粘贴 / 上传 claude_desktop_config.json 之类的 mcpServers 配置，
 * 导入前本地预解析给出预览（服务名 / 传输方式 / 目标 / 是否含密钥），导入后展示逐个结果。
 */
import { computed, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import type { UploadProps } from 'ant-design-vue'
import { UploadOutlined } from '@ant-design/icons-vue'

import { useMcpStore } from '@/stores/mcp'
import type { McpImportResult } from '@/types'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{
  (event: 'update:open', value: boolean): void
  (event: 'imported', result: McpImportResult): void
}>()

const store = useMcpStore()

const payload = ref('')
const strategy = ref<'skip' | 'overwrite' | 'rename'>('rename')
const autoTest = ref(true)
const visibleToUsers = ref(true)
const importing = ref(false)
const result = ref<McpImportResult | null>(null)

const strategyOptions = [
  { value: 'skip', label: '跳过已存在的服务' },
  { value: 'rename', label: '自动重命名（推荐）' },
  { value: 'overwrite', label: '覆盖已有配置' },
]

const previewColumns = [
  { title: '名称', key: 'name', width: 180 },
  { title: '传输方式', key: 'transport', width: 110 },
  { title: '目标', key: 'target', ellipsis: true },
  { title: '敏感', key: 'secret', width: 90 },
]

interface PreviewItem {
  name: string
  transport: string
  target: string
  hasSecret: boolean
}

const SECRET_RE = /(api[_-]?key|secret|token|password|authorization|auth)/i

/** 本地预解析（与后端保持一致的主要分支，仅用于导入前预览） */
const preview = computed<PreviewItem[]>(() => {
  const text = payload.value.trim()
  if (!text) return []
  let data: unknown
  try {
    data = JSON.parse(text)
  } catch {
    return []
  }

  let entries: Array<[string, Record<string, unknown>]> = []
  const looksLikeServer = (value: unknown): value is Record<string, unknown> =>
    Boolean(value && typeof value === 'object' && !Array.isArray(value) &&
      ['command', 'url', 'serverUrl', 'endpoint', 'type', 'transport'].some((key) => key in (value as object)))

  if (Array.isArray(data)) {
    entries = data.filter(looksLikeServer).map((item, index) => [String((item as Record<string, unknown>).name || `mcp-${index + 1}`), item as Record<string, unknown>])
  } else if (data && typeof data === 'object') {
    const obj = data as Record<string, unknown>
    for (const key of ['mcpServers', 'mcp_servers', 'servers']) {
      const wrapped = obj[key]
      if (wrapped && typeof wrapped === 'object' && !Array.isArray(wrapped)) {
        const inner = (wrapped as Record<string, unknown>).servers
        const target = inner && typeof inner === 'object' && !Array.isArray(inner) ? inner : wrapped
        entries = Object.entries(target as Record<string, Record<string, unknown>>).filter(([, value]) => value && typeof value === 'object')
        break
      }
    }
    if (!entries.length && obj.mcp && typeof obj.mcp === 'object') {
      const inner = (obj.mcp as Record<string, unknown>).servers
      if (inner && typeof inner === 'object') {
        entries = Object.entries(inner as Record<string, Record<string, unknown>>)
      }
    }
    if (!entries.length && looksLikeServer(obj)) {
      entries = [[String(obj.name || 'imported-mcp'), obj]]
    }
    if (!entries.length) {
      entries = Object.entries(obj).filter(([, value]) => looksLikeServer(value)) as Array<[string, Record<string, unknown>]>
    }
  }

  return entries.map(([name, spec]) => {
    const command = spec.command ? String(spec.command) : ''
    const args = Array.isArray(spec.args) ? (spec.args as string[]).join(' ') : ''
    const url = String(spec.url || spec.serverUrl || spec.endpoint || '')
    const typeHint = String(spec.type || spec.transport || '').toLowerCase()
    const transport = command ? 'stdio' : typeHint === 'sse' ? 'sse' : 'http'
    const env = (spec.env || spec.environment || {}) as Record<string, unknown>
    const headers = (spec.headers || {}) as Record<string, unknown>
    const hasSecret = [...Object.keys(env), ...Object.keys(headers)].some((key) => SECRET_RE.test(key))
    return {
      name,
      transport,
      target: command ? `${command} ${args}`.trim() : url,
      hasSecret,
    }
  })
})

watch(
  () => props.open,
  (open) => {
    if (open) {
      result.value = null
      if (!payload.value) payload.value = ''
    }
  },
)

function handleFile(file: File): boolean {
  const reader = new FileReader()
  reader.onload = () => {
    payload.value = String(reader.result || '')
    message.success(`已读取 ${file.name}`)
  }
  reader.onerror = () => message.error('文件读取失败')
  reader.readAsText(file, 'utf-8')
  return false
}

function fillExample() {
  payload.value = JSON.stringify(
    {
      mcpServers: {
        'amap-maps': {
          command: 'npx',
          args: ['-y', '@amap/amap-maps-mcp-server'],
          env: { AMAP_MAPS_API_KEY: '您在高德官网上申请的key' },
        },
      },
    },
    null,
    2,
  )
}

function actionLabel(action: string) {
  return { created: '新增', renamed: '新增（重命名）', updated: '覆盖', skipped: '跳过', failed: '失败' }[action] || action
}


async function submit() {
  const text = payload.value.trim()
  if (!text) {
    message.warning('请先粘贴或选择配置文件')
    return
  }
  if (!preview.value.length) {
    message.warning('没有识别到有效的 MCP 服务，请检查 JSON 格式')
    return
  }
  importing.value = true
  try {
    const imported = await store.importServers({
      payload: text,
      strategy: strategy.value,
      auto_test: autoTest.value,
      enabled: true,
      visible_to_users: visibleToUsers.value,
    })
    result.value = imported
    emit('imported', imported)
    if (imported.failed) message.warning(`导入完成，${imported.failed} 个失败`)
    else message.success(`导入完成：新增 ${imported.created}，覆盖 ${imported.updated}，跳过 ${imported.skipped}`)
  } finally {
    importing.value = false
  }
}

function close() {
  emit('update:open', false)
}

const uploadProps: UploadProps = {}
void uploadProps
</script>

<style scoped>
.mcp-import__tip {
  margin-bottom: 12px;
}

.mcp-import__toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.mcp-import__count {
  margin-left: auto;
  font-size: 12px;
}

textarea.mcp-import__editor {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 12px;
  line-height: 1.6;
}

.mcp-import__preview {
  margin-top: 12px;
}

.mcp-import__options {
  margin-top: 12px;
}

.mcp-import__divider {
  margin: 16px 0 12px;
  font-size: 13px;
  color: var(--text-secondary);
}

.mcp-import__results {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 260px;
  overflow-y: auto;
}

.mcp-result {
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
}

.mcp-result__head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.mcp-result__name {
  font-size: 13px;
  font-weight: 600;
}

.mcp-result__slug {
  font-size: 11px;
}

.mcp-result__tools {
  margin-left: auto;
  margin-inline-end: 0;
  font-size: 11px;
}

.mcp-result__message {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.mcp-result__tool-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.mcp-result__tool-list code {
  font-size: 11px;
  padding: 1px 6px;
  background: var(--bg-sunken);
  border-radius: 4px;
}
</style>
