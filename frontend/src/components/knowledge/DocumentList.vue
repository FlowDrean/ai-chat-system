<template>
  <div class="document-list">
    <div class="document-list__toolbar">
      <a-upload
        :show-upload-list="false"
        :before-upload="beforeUpload"
        :multiple="true"
        :accept="accept"
      >
        <a-button type="primary" :loading="uploading">
          <template #icon><UploadOutlined /></template>
          上传文档
        </a-button>
      </a-upload>
      <span class="document-list__hint">
        支持 {{ accept }} · 单文件不超过 {{ maxSizeMb }}MB
      </span>
      <a-button class="document-list__refresh" size="small" type="text" @click="emit('refresh')">
        <template #icon><ReloadOutlined /></template>
        刷新
      </a-button>
    </div>

    <a-progress
      v-if="uploading"
      :percent="uploadPercent"
      size="small"
      :status="uploadPercent >= 100 ? 'active' : 'normal'"
      class="document-list__progress"
    />

    <LoadingView v-if="loading && !documents.length" text="加载文档中…" />

    <EmptyState
      v-else-if="!documents.length"
      :icon="FileTextOutlined"
      title="还没有文档"
      description="上传 PDF / DOCX / TXT / Markdown / CSV / XLSX，AI 就能基于你的资料回答问题。"
    />

    <a-table
      v-else
      :data-source="documents"
      :columns="columns"
      :pagination="false"
      row-key="id"
      size="middle"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'filename'">
          <div class="doc-name">
            <FileTextOutlined class="doc-name__icon" />
            <span class="text-ellipsis">{{ record.filename }}</span>
          </div>
        </template>

        <template v-else-if="column.key === 'file_size'">
          {{ formatFileSize(record.file_size) }}
        </template>

        <template v-else-if="column.key === 'status'">
          <a-tag class="tag-mono">
            <span class="status-dot" :class="statusDotClass(record.status)" />
            {{ documentStatusText(record.status) }}
            <template v-if="isProcessing(record.status) && record.progress">
              {{ record.progress }}%
            </template>
          </a-tag>
          <a-tooltip v-if="record.error_message" :title="record.error_message">
            <ExclamationCircleOutlined class="doc-error" />
          </a-tooltip>
        </template>

        <template v-else-if="column.key === 'chunk_count'">
          {{ record.chunk_count || 0 }}
        </template>

        <template v-else-if="column.key === 'created_at'">
          {{ formatDateTime(record.created_at) }}
        </template>

        <template v-else-if="column.key === 'action'">
          <a-space :size="4">
            <a-button size="small" type="link" @click="emit('preview', record)">分块</a-button>
            <a-popconfirm
              title="重新向量化该文档？"
              ok-text="开始"
              cancel-text="取消"
              @confirm="emit('reindex', record)"
            >
              <a-button size="small" type="link">重新向量化</a-button>
            </a-popconfirm>
            <a-popconfirm
              title="确定删除该文档？"
              ok-text="删除"
              cancel-text="取消"
              @confirm="emit('delete', record)"
            >
              <a-button size="small" type="link" danger>删除</a-button>
            </a-popconfirm>
          </a-space>
        </template>
      </template>
    </a-table>
  </div>
</template>

<script setup lang="ts">
/** 文档列表：上传 / 处理状态 / 分块预览 / 重新向量化 / 删除 */
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import type { TableColumnsType, UploadProps } from 'ant-design-vue'
import {
  ExclamationCircleOutlined,
  FileTextOutlined,
  ReloadOutlined,
  UploadOutlined,
} from '@ant-design/icons-vue'

import EmptyState from '@/components/common/EmptyState.vue'
import LoadingView from '@/components/common/LoadingView.vue'
import type { DocumentItem } from '@/types'
import { documentStatusText, formatDateTime, formatFileSize } from '@/utils/format'

withDefaults(
  defineProps<{
    documents: DocumentItem[]
    loading?: boolean
    uploading?: boolean
    uploadPercent?: number
    accept?: string
    maxSizeMb?: number
  }>(),
  {
    loading: false,
    uploading: false,
    uploadPercent: 0,
    accept: '.pdf,.docx,.txt,.md,.csv,.xlsx',
    maxSizeMb: 50,
  },
)

const emit = defineEmits<{
  (event: 'upload', files: File[]): void
  (event: 'delete', document: DocumentItem): void
  (event: 'reindex', document: DocumentItem): void
  (event: 'preview', document: DocumentItem): void
  (event: 'refresh'): void
}>()

const pendingFiles = ref<File[]>([])

const columns: TableColumnsType = [
  { title: '文件名称', key: 'filename', dataIndex: 'filename', ellipsis: true },
  { title: '类型', key: 'file_type', dataIndex: 'file_type', width: 90 },
  { title: '大小', key: 'file_size', width: 100 },
  { title: '状态', key: 'status', width: 150 },
  { title: '分块', key: 'chunk_count', width: 80 },
  { title: '上传时间', key: 'created_at', width: 160 },
  { title: '操作', key: 'action', width: 220, fixed: 'right' },
]

function isProcessing(status: string) {
  return ['pending', 'parsing', 'splitting', 'embedding'].includes(status)
}

function statusDotClass(status: string) {
  if (status === 'completed') return 'is-ok'
  if (status === 'failed') return 'is-error'
  return 'is-busy'
}

const beforeUpload: UploadProps['beforeUpload'] = (file) => {
  const sizeMb = file.size / 1024 / 1024
  if (sizeMb > 50) {
    message.error(`${file.name} 超过 50MB 限制`)
    return false
  }
  pendingFiles.value = [file as unknown as File]
  emit('upload', pendingFiles.value)
  pendingFiles.value = []
  return false // 交给业务逻辑用 axios 上传（带进度与统一错误处理）
}
</script>

<style scoped>
.document-list__toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.document-list__hint {
  font-size: 12px;
  color: var(--text-secondary);
}

.document-list__refresh {
  margin-left: auto;
}

.document-list__progress {
  margin-bottom: 12px;
}

.doc-name {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.doc-name__icon {
  color: var(--brand);
}

.doc-error {
  margin-left: 6px;
  color: var(--error);
}
</style>
