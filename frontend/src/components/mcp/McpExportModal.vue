<template>
  <a-modal
    :open="open"
    title="导出 MCP 配置"
    :width="720"
    :footer="null"
    destroy-on-close
    @cancel="close"
  >
    <a-alert
      type="info"
      show-icon
      class="mcp-export__tip"
      message="导出为 mcpServers 格式，可直接粘贴到 Claude Desktop / Cursor 使用"
    />

    <div class="mcp-export__toolbar">
      <a-switch v-model:checked="includeSecrets" checked-children="含明文密钥" un-checked-children="密钥脱敏" />
      <span class="text-secondary mcp-export__hint">
        {{ includeSecrets ? '注意：导出内容包含真实密钥，请勿外传' : '默认脱敏，适合分享 / 排错' }}
      </span>
      <a-button type="primary" size="small" :disabled="!content" @click="copy">
        <template #icon><CopyOutlined /></template>
        复制 JSON
      </a-button>
    </div>

    <a-spin :spinning="loading">
      <pre class="mcp-export__content">{{ content || '（暂无可导出的服务）' }}</pre>
    </a-spin>

    <p class="text-secondary mcp-export__count">共 {{ count }} 个服务</p>
  </a-modal>
</template>

<script setup lang="ts">
/** MCP 配置导出弹窗：默认脱敏，可切换包含明文密钥（有风险提示） */
import { ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { CopyOutlined } from '@ant-design/icons-vue'

import { useMcpStore } from '@/stores/mcp'
import { copyToClipboard } from '@/utils/format'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (event: 'update:open', value: boolean): void }>()

const store = useMcpStore()
const loading = ref(false)
const content = ref('')
const count = ref(0)
const includeSecrets = ref(false)

async function load() {
  if (!props.open) return
  loading.value = true
  try {
    const result = await store.exportServers(includeSecrets.value)
    content.value = result.content
    count.value = result.count
  } finally {
    loading.value = false
  }
}

watch(() => [props.open, includeSecrets.value], load, { immediate: true })

async function copy() {
  try {
    await copyToClipboard(content.value)
    message.success('已复制到剪贴板')
  } catch {
    message.error('复制失败，请手动选择复制')
  }
}

function close() {
  emit('update:open', false)
}
</script>

<style scoped>
.mcp-export__tip {
  margin-bottom: 12px;
}

.mcp-export__toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.mcp-export__hint {
  font-size: 12px;
}

.mcp-export__content {
  margin: 0;
  max-height: 420px;
  overflow: auto;
  padding: 12px 14px;
  background: var(--bg-sunken);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  font-size: 12px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}

.mcp-export__count {
  margin: 8px 0 0;
  font-size: 12px;
}
</style>
