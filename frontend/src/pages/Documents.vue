<template>
  <AdminLayout>
    <div class="page-container">
      <div class="page-header">
        <div>
          <h1 class="page-title">文档管理</h1>
          <p class="page-subtitle">跨知识库查看所有文档的解析与向量化状态。</p>
        </div>
        <a-space>
          <a-select
            v-model:value="filters.status"
            :options="statusOptions"
            placeholder="全部状态"
            allow-clear
            style="width: 160px"
            @change="load"
          />
          <a-input
            v-model:value="filters.keyword"
            placeholder="按文件名搜索"
            allow-clear
            style="width: 200px"
            @press-enter="load"
          >
            <template #prefix><SearchOutlined /></template>
          </a-input>
          <a-button @click="load">
            <template #icon><ReloadOutlined /></template>
          </a-button>
        </a-space>
      </div>

      <a-card :bordered="true" size="small">
        <LoadingView v-if="loading && !documents.length" text="加载文档中…" />

        <EmptyState
          v-else-if="!documents.length"
          :icon="FileTextOutlined"
          title="还没有文档"
          description="进入某个知识库上传 PDF / DOCX / TXT / Markdown / CSV / XLSX 文件。"
        >
          <a-button type="primary" @click="router.push('/admin/knowledge')">前往知识库</a-button>
        </EmptyState>

        <a-table
          v-else
          :data-source="documents"
          :columns="columns"
          :loading="loading"
          :pagination="paginationConfig"
          row-key="id"
          size="middle"
          @change="handleTableChange"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'filename'">
              <div class="doc-name">
                <FileTextOutlined class="doc-name__icon" />
                <span class="text-ellipsis">{{ record.filename }}</span>
              </div>
            </template>

            <template v-else-if="column.key === 'knowledge_base_name'">
              <a-tag class="tag-mono">{{ record.knowledge_base_name }}</a-tag>
            </template>

            <template v-else-if="column.key === 'file_size'">
              {{ formatFileSize(record.file_size) }}
            </template>

            <template v-else-if="column.key === 'status'">
              <a-tag class="tag-mono">
                <span class="status-dot" :class="statusDotClass(record.status)" />
                {{ documentStatusText(record.status) }}
                <template v-if="isProcessing(record.status) && record.progress">{{ record.progress }}%</template>
              </a-tag>
              <a-tooltip v-if="record.error_message" :title="record.error_message">
                <ExclamationCircleOutlined class="doc-error" />
              </a-tooltip>
            </template>

            <template v-else-if="column.key === 'chunk_count'">{{ record.chunk_count || 0 }}</template>

            <template v-else-if="column.key === 'created_at'">{{ formatDateTime(record.created_at) }}</template>

            <template v-else-if="column.key === 'action'">
              <a-space :size="4">
                <a-button size="small" type="link" @click="router.push(`/admin/knowledge/${record.knowledge_base_id}`)">
                  查看知识库
                </a-button>
                <a-popconfirm title="重新向量化？" ok-text="开始" cancel-text="取消" @confirm="handleReindex(record)">
                  <a-button size="small" type="link">重新向量化</a-button>
                </a-popconfirm>
                <a-popconfirm title="确定删除？" ok-text="删除" cancel-text="取消" @confirm="handleDelete(record)">
                  <a-button size="small" type="link" danger>删除</a-button>
                </a-popconfirm>
              </a-space>
            </template>
          </template>
        </a-table>
      </a-card>
    </div>
  </AdminLayout>
</template>

<script setup lang="ts">
/** 文档管理：跨知识库查看 / 重新向量化 / 删除 */
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import type { TableColumnsType, TablePaginationConfig } from 'ant-design-vue'
import { ExclamationCircleOutlined, FileTextOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons-vue'
import { useRouter } from 'vue-router'

import EmptyState from '@/components/common/EmptyState.vue'
import LoadingView from '@/components/common/LoadingView.vue'
import AdminLayout from '@/layouts/AdminLayout.vue'
import { documentApi } from '@/api/knowledge'
import type { DocumentItem } from '@/types'
import { documentStatusText, formatDateTime, formatFileSize } from '@/utils/format'

const router = useRouter()

const documents = ref<DocumentItem[]>([])
const loading = ref(false)
const total = ref(0)
const filters = reactive<{ status?: string; keyword?: string }>({ status: undefined, keyword: undefined })
const page = reactive({ current: 1, pageSize: 10 })
let timer: number | null = null

const statusOptions = [
  { value: 'pending', label: '等待处理' },
  { value: 'parsing', label: '解析中' },
  { value: 'splitting', label: '切分中' },
  { value: 'embedding', label: '向量化中' },
  { value: 'completed', label: '处理完成' },
  { value: 'failed', label: '处理失败' },
]

const columns: TableColumnsType = [
  { title: '文件名称', key: 'filename', dataIndex: 'filename', ellipsis: true },
  { title: '知识库', key: 'knowledge_base_name', width: 160 },
  { title: '类型', key: 'file_type', dataIndex: 'file_type', width: 80 },
  { title: '大小', key: 'file_size', width: 100 },
  { title: '状态', key: 'status', width: 150 },
  { title: '分块', key: 'chunk_count', width: 80 },
  { title: '上传时间', key: 'created_at', width: 160 },
  { title: '操作', key: 'action', width: 240, fixed: 'right' },
]

const paginationConfig = computed<TablePaginationConfig>(() => ({
  current: page.current,
  pageSize: page.pageSize,
  total: total.value,
  showSizeChanger: true,
  showTotal: (value: number) => `共 ${value} 条`,
}))

function isProcessing(status: string) {
  return ['pending', 'parsing', 'splitting', 'embedding'].includes(status)
}

function statusDotClass(status: string) {
  if (status === 'completed') return 'is-ok'
  if (status === 'failed') return 'is-error'
  return 'is-busy'
}

async function load() {
  loading.value = true
  try {
    const data = await documentApi.listAll({
      page: page.current,
      page_size: page.pageSize,
      status: filters.status,
      keyword: filters.keyword,
    })
    documents.value = data.items
    total.value = data.meta.total
    const hasProcessing = documents.value.some((item) => isProcessing(item.status))
    if (hasProcessing && timer === null) {
      timer = window.setInterval(load, 3000)
    } else if (!hasProcessing && timer !== null) {
      window.clearInterval(timer)
      timer = null
    }
  } finally {
    loading.value = false
  }
}

function handleTableChange(pagination: TablePaginationConfig) {
  page.current = pagination.current || 1
  page.pageSize = pagination.pageSize || 10
  load()
}

async function handleReindex(document: DocumentItem) {
  await documentApi.reindex(document.id)
  message.success('已加入重新向量化队列')
  load()
}

async function handleDelete(document: DocumentItem) {
  await documentApi.remove(document.id)
  message.success('文档已删除')
  load()
}

onMounted(load)
onBeforeUnmount(() => {
  if (timer !== null) window.clearInterval(timer)
})
</script>

<style scoped>
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
