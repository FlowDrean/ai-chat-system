<template>
  <div class="rag-source">
    <div class="rag-source__title">
      <BookOutlined />
      <span>参考资料（{{ sources.length }}）</span>
    </div>
    <div class="rag-source__list">
      <button
        v-for="(source, index) in sources"
        :key="`${source.document_id}-${source.chunk_index}-${index}`"
        type="button"
        class="rag-source__item"
        @click="open(source, index)"
      >
        <span class="rag-source__index">{{ index + 1 }}</span>
        <span class="rag-source__file text-ellipsis">{{ source.filename || '未知文档' }}</span>
        <span v-if="source.page" class="rag-source__page">第 {{ source.page }} 页</span>
        <span class="rag-source__score">相似度 {{ (source.score ?? 0).toFixed(2) }}</span>
      </button>
    </div>

    <a-drawer
      v-model:open="visible"
      :title="active?.filename || '引用详情'"
      placement="right"
      :width="drawerWidth"
    >
      <template v-if="active">
        <a-descriptions :column="1" size="small" bordered>
          <a-descriptions-item label="文件名称">{{ active.filename || '-' }}</a-descriptions-item>
          <a-descriptions-item label="文件类型">{{ active.file_type || '-' }}</a-descriptions-item>
          <a-descriptions-item label="文档页码">{{ active.page ?? '-' }}</a-descriptions-item>
          <a-descriptions-item label="分块序号">{{ active.chunk_index ?? '-' }}</a-descriptions-item>
          <a-descriptions-item label="相似度">{{ (active.score ?? 0).toFixed(4) }}</a-descriptions-item>
        </a-descriptions>

        <div class="rag-source__section">
          <div class="rag-source__section-title">Chunk 内容</div>
          <MarkdownRenderer :content="active.content || ''" />
        </div>

        <div v-if="active.metadata" class="rag-source__section">
          <div class="rag-source__section-title">Metadata</div>
          <pre class="rag-source__meta mono">{{ JSON.stringify(active.metadata, null, 2) }}</pre>
        </div>
      </template>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
/** RAG 引用来源：卡片列表 + 详情抽屉（文件名 / 页码 / Chunk 内容 / 相似度 / Metadata） */
import { computed, ref } from 'vue'
import { BookOutlined } from '@ant-design/icons-vue'

import type { RagSource } from '@/types'
import MarkdownRenderer from './MarkdownRenderer.vue'

defineProps<{ sources: RagSource[] }>()

const visible = ref(false)
const active = ref<RagSource | null>(null)
const drawerWidth = computed(() => (window.innerWidth < 768 ? '100%' : 520))

function open(source: RagSource, _index: number) {
  active.value = source
  visible.value = true
}
</script>

<style scoped>
.rag-source {
  margin-top: 12px;
  padding: 10px 12px;
  background: var(--bg-sunken);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
}

.rag-source__title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 8px;
}

.rag-source__list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.rag-source__item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  padding: 6px 10px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 999px;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-primary);
  transition: var(--transition);
}

.rag-source__item:hover {
  border-color: var(--brand);
  color: var(--brand);
  background: var(--brand-soft);
}

.rag-source__index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--brand-soft);
  color: var(--brand);
  font-size: 11px;
  flex-shrink: 0;
}

.rag-source__file {
  max-width: 180px;
}

.rag-source__page,
.rag-source__score {
  color: var(--text-secondary);
}

.rag-source__section {
  margin-top: 18px;
}

.rag-source__section-title {
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
}

.rag-source__meta {
  max-height: 260px;
  overflow: auto;
  padding: 10px 12px;
  background: var(--bg-sunken);
  border-radius: var(--radius-sm);
  font-size: 12px;
  line-height: 1.6;
}
</style>
