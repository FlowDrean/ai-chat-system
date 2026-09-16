<template>
  <div class="chat-header">
    <div class="chat-header__left">
      <button type="button" class="chat-header__icon-btn" title="会话列表" @click="emit('toggle-sidebar')">
        <MenuOutlined />
      </button>
      <div class="chat-header__title">
        <span class="text-ellipsis">{{ title || '新对话' }}</span>
        <a-tag v-if="isRagEnabled" class="tag-mono chat-header__badge">RAG</a-tag>
      </div>
    </div>

    <div class="chat-header__right">
      <ModelSelector v-model="modelId" size="small" width="170px" />
      <KnowledgeSelector v-model="knowledgeBaseId" size="small" width="160px" />
      <PromptSelector v-model="promptId" size="small" width="150px" />
      <ThemeToggle />
      <a-tooltip title="模型参数">
        <button type="button" class="chat-header__icon-btn" @click="emit('open-params')">
          <SlidersOutlined />
        </button>
      </a-tooltip>
      <a-dropdown :trigger="['click']" placement="bottomRight">
        <button type="button" class="chat-header__icon-btn"><MoreOutlined /></button>
        <template #overlay>
          <a-menu @click="(info: MenuInfo) => emit('action', String(info.key))">
            <a-menu-item key="clear"><DeleteOutlined /> 清空当前对话</a-menu-item>
            <a-menu-item key="rename"><EditOutlined /> 重命名会话</a-menu-item>
            <a-menu-item key="knowledge"><DatabaseOutlined /> 管理知识库</a-menu-item>
            <a-menu-divider />
            <a-menu-item key="home"><HomeOutlined /> 返回首页</a-menu-item>
            <a-menu-item key="admin"><SettingOutlined /> 管理后台</a-menu-item>
          </a-menu>
        </template>
      </a-dropdown>
    </div>
  </div>
</template>

<script setup lang="ts">
/** 聊天页顶部：当前会话标题 + 模型 / 知识库 / Prompt 选择 + 更多操作 */
import { computed } from 'vue'
import {
  DatabaseOutlined,
  DeleteOutlined,
  EditOutlined,
  HomeOutlined,
  MenuOutlined,
  MoreOutlined,
  SettingOutlined,
  SlidersOutlined,
} from '@ant-design/icons-vue'

import ThemeToggle from '@/components/common/ThemeToggle.vue'
import { useKnowledgeStore } from '@/stores/knowledge'
import { useSettingsStore } from '@/stores/settings'
import KnowledgeSelector from './KnowledgeSelector.vue'
import ModelSelector from './ModelSelector.vue'
import PromptSelector from './PromptSelector.vue'
import type { MenuInfo } from 'ant-design-vue/es/menu/src/interface'

defineProps<{ title?: string | null }>()

const emit = defineEmits<{
  (event: 'toggle-sidebar'): void
  (event: 'open-params'): void
  (event: 'action', key: string): void
}>()

const settings = useSettingsStore()
const knowledgeStore = useKnowledgeStore()

const modelId = computed({
  get: () => settings.modelId,
  set: (value: number | null) => (settings.modelId = value),
})
const knowledgeBaseId = computed({
  get: () => settings.knowledgeBaseId,
  set: (value: number | null) => (settings.knowledgeBaseId = value),
})
const promptId = computed({
  get: () => settings.promptId,
  set: (value: number | null) => (settings.promptId = value),
})
const isRagEnabled = computed(
  () => Boolean(settings.knowledgeBaseId) && settings.autoRag && knowledgeStore.knowledgeBases.length > 0,
)
</script>

<style scoped>
.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  height: var(--header-height);
  padding: 0 16px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border-color);
}

.chat-header__left,
.chat-header__right {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.chat-header__left {
  flex: 1;
}

.chat-header__title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  min-width: 0;
  max-width: 46vw;
}

.chat-header__badge {
  font-size: 11px;
  margin-inline-end: 0;
}

.chat-header__icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 15px;
  transition: var(--transition);
}

.chat-header__icon-btn:hover {
  background: var(--bg-hover);
  color: var(--brand);
}

@media (max-width: 992px) {
  .chat-header__right :deep(.ant-select) {
    display: none;
  }
}
@media (max-width: 768px) {
  .chat-header {
    padding: 0 10px;
  }
  .chat-header__title {
    max-width: 40vw;
  }
}
</style>
