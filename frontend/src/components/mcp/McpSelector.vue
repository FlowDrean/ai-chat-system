<template>
  <a-popover v-model:open="open" trigger="click" placement="topRight" :overlay-style="{ width: '380px' }">
    <template #content>
      <div class="mcp-selector__panel">
        <div class="mcp-selector__head">
          <div>
            <strong>MCP 工具</strong>
            <p class="mcp-selector__desc">勾选 MCP 服务后，模型可调用其暴露的工具</p>
          </div>
          <a-button v-if="selected.length" type="link" size="small" @click="clearAll">清空</a-button>
        </div>

        <a-spin :spinning="store.loading">
          <EmptyState
            v-if="!store.available.length"
            :icon="ApiOutlined"
            title="暂无可用的 MCP 服务"
            description="先到「MCP 管理」接入服务并测试连接。"
          >
            <a-button size="small" type="primary" @click="goManage">去接入</a-button>
          </EmptyState>

          <div v-else class="mcp-selector__list">
            <label v-for="item in store.available" :key="item.id" class="mcp-selector__item">
              <a-checkbox
                :checked="selected.includes(item.id)"
                @change="(event: CheckboxChangeEvent) => toggle(item, event)"
              />
              <div class="mcp-selector__info">
                <div class="mcp-selector__name">
                  <span>{{ item.name }}</span>
                  <a-tag class="tag-mono mcp-selector__tag">
                    {{ item.tool_count }} 工具
                  </a-tag>
                </div>
                <p class="mcp-selector__text">{{ item.description || '暂无说明' }}</p>
              </div>
            </label>
          </div>
        </a-spin>

        <div class="mcp-selector__footer">
          <span class="text-secondary">已选 {{ selected.length }} 个服务</span>
          <a-button type="link" size="small" @click="goManage">管理 MCP</a-button>
        </div>
      </div>
    </template>

    <a-tooltip :title="selected.length ? `已启用 ${selected.length} 个 MCP 服务` : '选择 MCP 服务'">
      <button type="button" class="tool-btn" :class="{ active: selected.length > 0 }">
        <ApiOutlined />
        <span v-if="selected.length" class="tool-btn__badge">{{ selected.length }}</span>
      </button>
    </a-tooltip>
  </a-popover>
</template>

<script setup lang="ts">
/**
 * MCP 服务选择器（聊天输入框工具栏）
 * 选中的服务随请求发送（mcp_server_ids）并保存到会话上，下次进入自动恢复。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ApiOutlined } from '@ant-design/icons-vue'
import type { CheckboxChangeEvent } from 'ant-design-vue/es/checkbox/interface'

import EmptyState from '@/components/common/EmptyState.vue'
import { useMcpStore } from '@/stores/mcp'
import type { McpServerOption } from '@/types'

const props = defineProps<{ modelValue?: number[] | null }>()
const emit = defineEmits<{ (event: 'update:modelValue', value: number[]): void }>()

const router = useRouter()
const store = useMcpStore()
const open = ref(false)

const selected = computed(() => props.modelValue || [])

onMounted(() => {
  store.fetchAvailable().catch(() => undefined)
})

function toggle(item: McpServerOption, event: CheckboxChangeEvent) {
  const next = new Set(selected.value)
  if (event.target.checked) next.add(item.id)
  else next.delete(item.id)
  emit('update:modelValue', [...next])
}

function clearAll() {
  emit('update:modelValue', [])
}

function goManage() {
  open.value = false
  router.push('/admin/mcp')
}
</script>

<style scoped>
.mcp-selector__panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.mcp-selector__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.mcp-selector__desc {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.mcp-selector__list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 320px;
  overflow-y: auto;
}

.mcp-selector__item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px;
  border-radius: 8px;
  cursor: pointer;
  transition: background var(--transition);
}

.mcp-selector__item:hover {
  background: var(--bg-hover);
}

.mcp-selector__info {
  min-width: 0;
}

.mcp-selector__name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
}

.mcp-selector__tag {
  font-size: 11px;
  margin-inline-end: 0;
}

.mcp-selector__text {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.mcp-selector__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 8px;
  border-top: 1px solid var(--border-color);
  font-size: 12px;
}

.tool-btn__badge {
  position: absolute;
  top: 1px;
  right: 2px;
  min-width: 14px;
  height: 14px;
  padding: 0 3px;
  border-radius: 7px;
  background: var(--brand);
  color: var(--brand-contrast);
  font-size: 10px;
  line-height: 14px;
  text-align: center;
}
</style>
