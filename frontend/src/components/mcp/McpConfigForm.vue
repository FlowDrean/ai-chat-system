<template>
  <a-drawer
    :open="open"
    :title="isEdit ? `配置 MCP 服务：${current?.name}` : '接入 MCP 服务'"
    placement="right"
    :width="720"
    destroy-on-close
    @close="close"
  >
    <a-form ref="formRef" :model="form" :rules="rules" layout="vertical">
      <a-row :gutter="16">
        <a-col :xs="24" :md="12">
          <a-form-item label="服务名称" name="name">
            <a-input v-model:value="form.name" :maxlength="32" placeholder="例如：文件系统 / GitHub" />
          </a-form-item>
        </a-col>
        <a-col :xs="24" :md="12">
          <a-form-item label="传输方式" name="transport">
            <a-select
              v-model:value="form.transport"
              :options="transportOptions"
              :disabled="isEdit && false"
              @change="handleTransportChange"
            />
          </a-form-item>
        </a-col>
        <a-col :span="24">
          <a-form-item label="说明（会拼进工具描述，帮助模型判断何时调用）">
            <a-textarea v-model:value="form.description" :rows="2" :maxlength="500" placeholder="可选" />
          </a-form-item>
        </a-col>
      </a-row>

      <!-- stdio -->
      <template v-if="form.transport === 'stdio'">
        <a-divider orientation="left" class="mcp-form__divider">进程配置</a-divider>
        <a-form-item label="启动命令" name="command" required>
          <a-input v-model:value="form.command" placeholder="npx / python / uvx / node ..." />
        </a-form-item>
        <a-form-item label="命令参数">
          <a-select
            v-model:value="argsList"
            mode="tags"
            :token-separators="[',']"
            placeholder="输入后回车添加，例如 -y @modelcontextprotocol/server-filesystem D:\\data"
          />
          <p class="mcp-form__help">
            常见示例：<code>npx -y @modelcontextprotocol/server-filesystem D:\资料</code>
          </p>
        </a-form-item>
        <a-form-item label="环境变量（JSON）">
          <a-textarea v-model:value="envText" :rows="3" class="mcp-form__mono" placeholder='{"API_KEY": "xxx"}' />
          <p class="mcp-form__help">敏感值（KEY / TOKEN / SECRET / PASSWORD）加密存储，导出时脱敏；留空表示不修改</p>
        </a-form-item>
        <a-form-item label="工作目录">
          <a-input v-model:value="form.cwd" placeholder="可选，默认当前后端目录" />
        </a-form-item>
      </template>

      <!-- sse / http -->
      <template v-else>
        <a-divider orientation="left" class="mcp-form__divider">远程连接</a-divider>
        <a-form-item label="服务地址" name="url" required>
          <a-input
            v-model:value="form.url"
            :placeholder="form.transport === 'sse' ? 'https://example.com/sse' : 'https://example.com/mcp'"
          />
        </a-form-item>
        <a-form-item label="请求头（JSON）">
          <a-textarea
            v-model:value="headersText"
            :rows="3"
            class="mcp-form__mono"
            placeholder='{"Authorization": "Bearer xxx"}'
          />
          <p class="mcp-form__help">Authorization / Token 等敏感值加密存储并脱敏输出</p>
        </a-form-item>
      </template>

      <a-divider orientation="left" class="mcp-form__divider">通用设置</a-divider>
      <a-row :gutter="16">
        <a-col :xs="12" :md="8">
          <a-form-item label="启用">
            <a-switch v-model:checked="form.enabled" />
          </a-form-item>
        </a-col>
        <a-col :xs="12" :md="8">
          <a-form-item label="允许用户在聊天中选择">
            <a-switch v-model:checked="form.visible_to_users" />
          </a-form-item>
        </a-col>
        <a-col :xs="12" :md="8">
          <a-form-item label="超时（秒）">
            <a-input-number v-model:value="form.timeout" :min="5" :max="600" style="width: 100%" />
          </a-form-item>
        </a-col>
      </a-row>

      <a-alert type="info" show-icon :message="transportHint" class="mcp-form__hint" />
    </a-form>

    <!-- 连接测试 -->
    <a-divider orientation="left" class="mcp-form__divider">连接测试</a-divider>
    <a-space>
      <a-button :disabled="!isEdit" :loading="testing" @click="runTest">
        <template #icon><ApiOutlined /></template>
        测试连接并发现工具
      </a-button>
      <span v-if="!isEdit" class="mcp-form__help">先保存，再测试连接</span>
    </a-space>

    <a-alert
      v-if="testResult"
      class="mcp-form__result"
      :type="testResult.success ? 'success' : 'error'"
      show-icon
      :message="testResult.success ? `连接成功：发现 ${testResult.tool_count} 个工具（${testResult.latency_ms}ms）` : testResult.message"
    />

    <div v-if="tools.length" class="mcp-form__tools">
      <div v-for="tool in tools" :key="tool.name" class="mcp-tool">
        <div class="mcp-tool__head">
          <span class="mcp-tool__name">{{ tool.name }}</span>
          <a-button size="small" type="link" @click="openDebug(tool)">调试调用</a-button>
        </div>
        <p class="mcp-tool__desc">{{ tool.description || '（无描述）' }}</p>
        <div class="mcp-tool__schema">
          <span class="mcp-tool__label">入参</span>
          <code>{{ Object.keys((tool.input_schema?.properties as Record<string, unknown>) || {}).join(', ') || '无' }}</code>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="mcp-form__footer">
        <a-button @click="close">取消</a-button>
        <a-button type="primary" :loading="saving" @click="submit">保存</a-button>
      </div>
    </template>

    <!-- 工具调试调用 -->
    <a-modal
      v-model:open="debugOpen"
      :title="`调试调用：${debugTool?.name || ''}`"
      :footer="null"
      :width="620"
    >
      <a-form layout="vertical">
        <a-form-item v-for="arg in debugArgs" :key="arg.name" :label="`${arg.name}（${arg.type}）`">
          <a-input v-model:value="debugValues[arg.name]" :placeholder="arg.description" />
        </a-form-item>
        <a-button type="primary" :loading="calling" @click="submitDebug">
          <template #icon><PlayCircleOutlined /></template>
          调用
        </a-button>
      </a-form>
      <a-alert
        v-if="debugResult"
        class="mcp-form__result"
        :type="debugResult.success ? 'success' : 'error'"
        show-icon
        :message="debugResult.success ? `调用成功（${debugResult.latency_ms}ms）` : debugResult.error || '调用失败'"
      >
        <template v-if="debugResult.output" #description>
          <pre class="mcp-form__output">{{ debugResult.output }}</pre>
        </template>
      </a-alert>
    </a-modal>
  </a-drawer>
</template>

<script setup lang="ts">
/**
 * MCP 服务配置表单
 * 按传输方式（stdio / sse / http）动态切换字段；保存后可一键测试连接并发现工具。
 */
import { computed, reactive, ref, watch } from 'vue'
import type { FormInstance } from 'ant-design-vue'
import type { Rule } from 'ant-design-vue/es/form'
import { message } from 'ant-design-vue'
import { ApiOutlined, PlayCircleOutlined } from '@ant-design/icons-vue'

import { useMcpStore } from '@/stores/mcp'
import type { McpServerItem, McpServerPayload, McpTestResult, McpTool, McpToolCallResult } from '@/types'

const props = defineProps<{ open: boolean; current?: McpServerItem | null }>()
const emit = defineEmits<{
  (event: 'update:open', value: boolean): void
  (event: 'saved', server?: McpServerItem): void
}>()

const store = useMcpStore()
const formRef = ref<FormInstance>()
const saving = ref(false)
const testing = ref(false)
const calling = ref(false)
const testResult = ref<McpTestResult | null>(null)
const tools = ref<McpTool[]>([])
const debugOpen = ref(false)
const debugTool = ref<McpTool | null>(null)
const debugResult = ref<McpToolCallResult | null>(null)
const debugValues = reactive<Record<string, string>>({})

const isEdit = computed(() => Boolean(props.current?.id))
const argsList = ref<string[]>([])
const envText = ref('')
const headersText = ref('')

const form = reactive<McpServerPayload>({
  name: '',
  transport: 'stdio',
  command: '',
  args: [],
  cwd: '',
  url: '',
  enabled: true,
  visible_to_users: true,
  timeout: 60,
  sort_order: 0,
})

const rules: Record<string, Rule[]> = {
  name: [{ required: true, message: '请输入服务名称', trigger: 'blur' }],
  command: [{ required: true, message: '请输入启动命令', trigger: 'blur' }],
  url: [{ required: true, message: '请输入服务地址', trigger: 'blur' }],
}

const transportOptions = computed(() =>
  store.transports.map((item) => ({ value: item.value, label: item.label })),
)

const transportHint = computed(
  () => store.transports.find((item) => item.value === form.transport)?.description || '',
)

const debugArgs = computed(() => {
  const schema = (debugTool.value?.input_schema || {}) as Record<string, unknown>
  const properties = (schema.properties || {}) as Record<string, Record<string, unknown>>
  const required = new Set((schema.required as string[]) || [])
  return Object.entries(properties).map(([name, spec]) => ({
    name,
    type: String(spec?.type || 'string'),
    description: String(spec?.description || ''),
    required: required.has(name),
  }))
})

function reset() {
  const current = props.current
  form.name = current?.name || ''
  form.transport = current?.transport || 'stdio'
  form.command = current?.command || ''
  form.cwd = current?.cwd || ''
  form.url = current?.url || ''
  form.enabled = current?.enabled ?? true
  form.visible_to_users = current?.visible_to_users ?? true
  form.timeout = current?.timeout ?? 60
  form.sort_order = current?.sort_order ?? 0
  argsList.value = current?.args ? [...current.args] : []
  envText.value = current?.env ? JSON.stringify(current.env, null, 2) : ''
  headersText.value = current?.headers ? JSON.stringify(current.headers, null, 2) : ''
  testResult.value = null
  tools.value = current?.tools ? [...current.tools] : []
}

watch(() => [props.open, props.current?.id], reset, { immediate: true })

function handleTransportChange() {
  testResult.value = null
  tools.value = []
}

function parseJsonObject(text: string, label: string): Record<string, string> | null {
  const trimmed = text.trim()
  if (!trimmed) return null
  try {
    const parsed = JSON.parse(trimmed)
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return Object.fromEntries(Object.entries(parsed).map(([k, v]) => [k, v === null ? '' : String(v)]))
    }
    message.error(`${label} 必须是 JSON 对象`)
    return null
  } catch {
    message.error(`${label} 不是合法 JSON`)
    return null
  }
}

function buildPayload(): McpServerPayload {
  return {
    ...form,
    args: form.transport === 'stdio' ? argsList.value : null,
    env: form.transport === 'stdio' ? parseJsonObject(envText.value, '环境变量') : null,
    headers: form.transport === 'stdio' ? null : parseJsonObject(headersText.value, '请求头'),
    cwd: form.transport === 'stdio' ? form.cwd || null : null,
    url: form.transport === 'stdio' ? null : form.url || null,
    command: form.transport === 'stdio' ? form.command || null : null,
  }
}

async function submit() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  const payload = buildPayload()
  if (payload.env === null && form.transport === 'stdio' && envText.value.trim()) return
  if (payload.headers === null && form.transport !== 'stdio' && headersText.value.trim()) return

  saving.value = true
  try {
    if (isEdit.value && props.current) {
      const updated = await store.updateServer(props.current.id, payload)
      message.success('MCP 服务已更新')
      emit('saved', updated)
    } else {
      const created = await store.createServer(payload)
      message.success('MCP 服务已创建')
      emit('saved', created)
    }
    close()  // 保存后关闭抽屉，回到列表点「测试连接」验证
  } finally {
    saving.value = false
  }
}

async function runTest() {
  if (!props.current?.id) return
  testing.value = true
  try {
    const result = await store.testServer(props.current.id)
    testResult.value = result
    tools.value = result.tools
    if (result.success) message.success(`连接成功，发现 ${result.tool_count} 个工具`)
    else message.error(result.message)
  } finally {
    testing.value = false
  }
}

function openDebug(tool: McpTool) {
  debugTool.value = tool
  debugResult.value = null
  Object.keys(debugValues).forEach((key) => delete debugValues[key])
  for (const arg of debugArgs.value) debugValues[arg.name] = ''
  debugOpen.value = true
}

async function submitDebug() {
  if (!props.current?.id || !debugTool.value) return
  const args: Record<string, unknown> = {}
  for (const arg of debugArgs.value) {
    const value = debugValues[arg.name]
    args[arg.name] =
      (arg.type === 'integer' || arg.type === 'number') && value !== '' ? Number(value) : value
  }
  calling.value = true
  try {
    debugResult.value = await store.callTool(props.current.id, debugTool.value.name, args)
  } finally {
    calling.value = false
  }
}

function close() {
  emit('update:open', false)
}
</script>

<style scoped>
.mcp-form__divider {
  margin: 8px 0 16px;
  font-size: 13px;
  color: var(--text-secondary);
}

.mcp-form__help {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}

textarea.mcp-form__mono {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 12px;
}

.mcp-form__hint {
  margin-top: 4px;
}

.mcp-form__result {
  margin-top: 12px;
}

.mcp-form__output {
  margin: 0;
  max-height: 220px;
  overflow: auto;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
}

.mcp-form__tools {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.mcp-tool {
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
}

.mcp-tool__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.mcp-tool__name {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 13px;
  font-weight: 600;
}

.mcp-tool__desc {
  margin: 4px 0 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

.mcp-tool__schema {
  display: flex;
  gap: 8px;
  font-size: 12px;
}

.mcp-tool__label {
  color: var(--text-tertiary);
}

.mcp-form__footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
