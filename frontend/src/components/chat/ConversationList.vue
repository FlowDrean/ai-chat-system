<template>
  <div class="conversation-list">
    <div class="conversation-list__top">
      <a-button type="primary" block @click="emit('create')">
        <template #icon><PlusOutlined /></template>
        新建聊天
      </a-button>
      <a-input
        v-model:value="keyword"
        class="conversation-list__search"
        placeholder="搜索会话"
        allow-clear
        size="small"
      >
        <template #prefix><SearchOutlined /></template>
      </a-input>
    </div>

    <div class="conversation-list__scroll">
      <LoadingView v-if="loading && !conversations.length" text="加载会话中…" min-height="120px" />

      <EmptyState
        v-else-if="!filtered.length"
        :icon="MessageOutlined"
        title="还没有聊天记录"
        description="开始你的第一次 AI 对话吧。"
      >
        <a-button type="primary" size="small" @click="emit('create')">开始聊天</a-button>
      </EmptyState>

      <template v-else>
        <template v-for="group in grouped" :key="group.label">
          <div class="conversation-list__group">{{ group.label }}</div>
          <div
            v-for="item in group.items"
            :key="item.id"
            class="conversation-list__item"
            :class="{ active: item.id === activeId }"
            @click="emit('select', item.id)"
          >
            <div class="conversation-list__main">
              <StarFilled v-if="item.is_favorite" class="conversation-list__star" />
              <span class="conversation-list__title text-ellipsis">{{ item.title }}</span>
            </div>
            <a-dropdown :trigger="['click']" placement="bottomRight">
              <button type="button" class="conversation-list__more" @click.stop>
                <MoreOutlined />
              </button>
              <template #overlay>
                <a-menu @click="(info: MenuInfo) => handleAction(String(info.key), item)">
                  <a-menu-item key="rename"><EditOutlined /> 重命名</a-menu-item>
                  <a-menu-item key="favorite">
                    <StarOutlined /> {{ item.is_favorite ? '取消收藏' : '收藏' }}
                  </a-menu-item>
                  <a-menu-item key="archive">
                    <InboxOutlined /> {{ item.is_archived ? '取消归档' : '归档' }}
                  </a-menu-item>
                  <a-menu-divider />
                  <a-menu-item key="delete" danger><DeleteOutlined /> 删除</a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
          </div>
        </template>
      </template>
    </div>

    <a-modal v-model:open="renameVisible" title="重命名会话" @ok="submitRename">
      <a-input v-model:value="renameValue" :maxlength="60" placeholder="请输入会话名称" @press-enter="submitRename" />
    </a-modal>
  </div>
</template>

<script setup lang="ts">
/** 会话列表：搜索 / 分组 / 重命名 / 收藏 / 归档 / 删除 */
import { computed, ref } from 'vue'
import { Modal } from 'ant-design-vue'
import {
  MessageOutlined,
  DeleteOutlined,
  EditOutlined,
  InboxOutlined,
  MoreOutlined,
  PlusOutlined,
  SearchOutlined,
  StarFilled,
  StarOutlined,
} from '@ant-design/icons-vue'

import EmptyState from '@/components/common/EmptyState.vue'
import LoadingView from '@/components/common/LoadingView.vue'
import type { Conversation } from '@/types'
import { groupByDay } from '@/utils/format'
import type { MenuInfo } from 'ant-design-vue/es/menu/src/interface'

const props = defineProps<{
  conversations: Conversation[]
  activeId?: number | null
  loading?: boolean
}>()

const emit = defineEmits<{
  (event: 'create'): void
  (event: 'select', id: number): void
  (event: 'rename', payload: { id: number; title: string }): void
  (event: 'favorite', conversation: Conversation): void
  (event: 'archive', conversation: Conversation): void
  (event: 'delete', conversation: Conversation): void
}>()

const keyword = ref('')
const renameVisible = ref(false)
const renameValue = ref('')
const renameTarget = ref<Conversation | null>(null)

const filtered = computed(() => {
  const key = keyword.value.trim().toLowerCase()
  if (!key) return props.conversations
  return props.conversations.filter((item) => item.title.toLowerCase().includes(key))
})

const grouped = computed(() =>
  groupByDay(filtered.value.filter((item) => !item.is_archived)).map((group) => ({
    label: group.label,
    items: group.items,
  })),
)

function handleAction(key: string, conversation: Conversation) {
  if (key === 'rename') {
    renameTarget.value = conversation
    renameValue.value = conversation.title
    renameVisible.value = true
  } else if (key === 'favorite') {
    emit('favorite', conversation)
  } else if (key === 'archive') {
    emit('archive', conversation)
  } else if (key === 'delete') {
    Modal.confirm({
      title: '删除会话',
      content: `确定删除「${conversation.title}」吗？该会话下的所有消息都会被删除。`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: () => emit('delete', conversation),
    })
  }
}

function submitRename() {
  const title = renameValue.value.trim()
  if (!title || !renameTarget.value) return
  emit('rename', { id: renameTarget.value.id, title })
  renameVisible.value = false
}
</script>

<style scoped>
.conversation-list {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.conversation-list__top {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  border-bottom: 1px solid var(--border-color);
}

.conversation-list__scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px 8px 20px;
}

.conversation-list__group {
  padding: 10px 8px 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

.conversation-list__item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 8px 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  transition: background var(--transition);
}

.conversation-list__item:hover {
  background: var(--bg-hover);
}

.conversation-list__item.active {
  background: var(--brand-soft);
}

.conversation-list__main {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  flex: 1;
}

.conversation-list__star {
  color: var(--text-primary);
  font-size: 12px;
  flex-shrink: 0;
}

.conversation-list__title {
  font-size: 13px;
  color: var(--text-primary);
}

.conversation-list__item.active .conversation-list__title {
  color: var(--brand);
  font-weight: 500;
}

.conversation-list__more {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  opacity: 0;
  transition: var(--transition);
}

.conversation-list__item:hover .conversation-list__more {
  opacity: 1;
}

.conversation-list__more:hover {
  background: var(--bg-card);
  color: var(--brand);
}
</style>
