<template>
  <div class="knowledge-card" @click="emit('open', kb)">
    <div class="knowledge-card__head">
      <span class="knowledge-card__icon"><DatabaseOutlined /></span>
      <a-dropdown :trigger="['click']" placement="bottomRight">
        <button type="button" class="knowledge-card__more" @click.stop><MoreOutlined /></button>
        <template #overlay>
          <a-menu @click="(info: MenuInfo) => handleAction(String(info.key))">
            <a-menu-item key="open"><EyeOutlined /> 查看详情</a-menu-item>
            <a-menu-item key="edit"><EditOutlined /> 编辑配置</a-menu-item>
            <a-menu-item key="test"><ExperimentOutlined /> 测试检索</a-menu-item>
            <a-menu-divider />
            <a-menu-item key="delete" danger><DeleteOutlined /> 删除知识库</a-menu-item>
          </a-menu>
        </template>
      </a-dropdown>
    </div>

    <h4 class="knowledge-card__title text-ellipsis">{{ kb.name }}</h4>
    <p class="knowledge-card__desc">{{ kb.description || '暂无描述' }}</p>

    <div class="knowledge-card__stats">
      <span><FileTextOutlined /> {{ kb.document_count }} 文档</span>
      <span><BlockOutlined /> {{ kb.chunk_count }} 分块</span>
      <span><ThunderboltOutlined /> Top {{ kb.top_k }}</span>
    </div>

    <div class="knowledge-card__footer">
      <a-tag class="tag-mono knowledge-card__tag">{{ kb.embedding_model }}</a-tag>
      <a-tag v-if="kb.rerank_enabled" class="knowledge-card__tag">ReRank</a-tag>
      <span class="knowledge-card__time">{{ formatRelative(kb.updated_at) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
/** 知识库卡片 */
import { Modal } from 'ant-design-vue'
import {
  BlockOutlined,
  DatabaseOutlined,
  DeleteOutlined,
  EditOutlined,
  ExperimentOutlined,
  EyeOutlined,
  FileTextOutlined,
  MoreOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons-vue'

import type { KnowledgeBase } from '@/types'
import { formatRelative } from '@/utils/format'
import type { MenuInfo } from 'ant-design-vue/es/menu/src/interface'

const props = defineProps<{ kb: KnowledgeBase }>()

const emit = defineEmits<{
  (event: 'open', kb: KnowledgeBase): void
  (event: 'edit', kb: KnowledgeBase): void
  (event: 'test', kb: KnowledgeBase): void
  (event: 'delete', kb: KnowledgeBase): void
}>()

function handleAction(key: string) {
  if (key === 'open') emit('open', props.kb)
  else if (key === 'edit') emit('edit', props.kb)
  else if (key === 'test') emit('test', props.kb)
  else if (key === 'delete') {
    Modal.confirm({
      title: '删除知识库',
      content: `确定删除「${props.kb.name}」吗？其中的 ${props.kb.document_count} 个文档与向量数据都会被删除，且不可恢复。`,
      okText: '删除',
      okType: 'danger',
      cancelText: '取消',
      onOk: () => emit('delete', props.kb),
    })
  }
}
</script>

<style scoped>
.knowledge-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  cursor: pointer;
  transition: var(--transition);
}

.knowledge-card:hover {
  border-color: var(--border-dark);
  box-shadow: var(--shadow-pop);
}

.knowledge-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.knowledge-card__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 9px;
  background: var(--brand-soft);
  color: var(--brand);
  font-size: 16px;
}

.knowledge-card__more {
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  width: 26px;
  height: 26px;
  border-radius: 6px;
  opacity: 0;
  transition: var(--transition);
}

.knowledge-card:hover .knowledge-card__more {
  opacity: 1;
}

.knowledge-card__more:hover {
  background: var(--bg-hover);
}

.knowledge-card__title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.knowledge-card__desc {
  margin: 0;
  min-height: 40px;
  font-size: 12px;
  color: var(--text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.knowledge-card__stats {
  display: flex;
  gap: 14px;
  font-size: 12px;
  color: var(--text-secondary);
}

.knowledge-card__stats span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.knowledge-card__footer {
  display: flex;
  align-items: center;
  gap: 6px;
  padding-top: 8px;
  border-top: 1px dashed var(--border-color);
}

.knowledge-card__tag {
  font-size: 11px;
  margin-inline-end: 0;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.knowledge-card__time {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-tertiary);
}
</style>
