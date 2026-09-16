<template>
  <AdminLayout>
    <div class="page-container">
      <a-spin :spinning="loading">
        <div class="page-header">
          <div>
            <a-space>
              <a-button type="text" @click="router.push('/admin/knowledge')">
                <template #icon><ArrowLeftOutlined /></template>
                返回
              </a-button>
              <h1 class="page-title">{{ kb?.name || '知识库详情' }}</h1>
              <a-tag v-if="kb" class="tag-mono">{{ kb.embedding_model }}</a-tag>
            </a-space>
            <p class="page-subtitle">{{ kb?.description || '暂无描述' }}</p>
          </div>
          <a-space>
            <a-button @click="openEdit">
              <template #icon><SettingOutlined /></template>
              编辑配置
            </a-button>
            <a-button @click="openTest">
              <template #icon><ExperimentOutlined /></template>
              检索测试
            </a-button>
          </a-space>
        </div>

        <!-- 基本信息 / Embedding / Chunk / Retriever -->
        <div v-if="kb" class="kb-detail__grid">
          <a-card title="基本信息" size="small" :bordered="true">
            <a-descriptions :column="1" size="small">
              <a-descriptions-item label="知识库名称">{{ kb.name }}</a-descriptions-item>
              <a-descriptions-item label="描述">{{ kb.description || '-' }}</a-descriptions-item>
              <a-descriptions-item label="文档数量">{{ kb.document_count }}</a-descriptions-item>
              <a-descriptions-item label="向量分块">{{ kb.chunk_count }}</a-descriptions-item>
              <a-descriptions-item label="创建时间">{{ formatDateTime(kb.created_at) }}</a-descriptions-item>
              <a-descriptions-item label="更新时间">{{ formatDateTime(kb.updated_at) }}</a-descriptions-item>
            </a-descriptions>
          </a-card>

          <a-card title="Embedding 配置" size="small" :bordered="true">
            <a-descriptions :column="1" size="small">
              <a-descriptions-item label="供应商">{{ kb.embedding_provider }}</a-descriptions-item>
              <a-descriptions-item label="模型">{{ kb.embedding_model }}</a-descriptions-item>
              <a-descriptions-item label="向量维度">{{ kb.embedding_dimension }}</a-descriptions-item>
              <a-descriptions-item label="Base URL">{{ kb.embedding_base_url || '默认' }}</a-descriptions-item>
              <a-descriptions-item label="API Key">
                <span class="mono">{{ kb.embedding_api_key_masked || '未配置' }}</span>
              </a-descriptions-item>
            </a-descriptions>
            <a-button size="small" type="link" :loading="checking" @click="checkEmbedding">
              校验 Embedding 配置
            </a-button>
          </a-card>

          <a-card title="Chunk 配置" size="small" :bordered="true">
            <a-descriptions :column="1" size="small">
              <a-descriptions-item label="Chunk Size">{{ kb.chunk_size }}</a-descriptions-item>
              <a-descriptions-item label="Chunk Overlap">{{ kb.chunk_overlap }}</a-descriptions-item>
            </a-descriptions>
          </a-card>

          <a-card title="Retriever 配置" size="small" :bordered="true">
            <a-descriptions :column="1" size="small">
              <a-descriptions-item label="Top K">{{ kb.top_k }}</a-descriptions-item>
              <a-descriptions-item label="相似度阈值">{{ kb.similarity_threshold }}</a-descriptions-item>
              <a-descriptions-item label="ReRank">{{ kb.rerank_enabled ? '已启用' : '未启用' }}</a-descriptions-item>
            </a-descriptions>
          </a-card>
        </div>

        <!-- 文档列表 -->
        <a-card title="文档列表" size="small" :bordered="true" class="kb-detail__documents">
          <DocumentList
            :documents="documents"
            :loading="documentsLoading"
            :uploading="uploading"
            :upload-percent="uploadPercent"
            :max-size-mb="limits.max_upload_size_mb"
            :accept="limits.allowed_extensions.join(',')"
            @upload="handleUpload"
            @delete="handleDelete"
            @reindex="handleReindex"
            @preview="openChunks"
            @refresh="loadDocuments"
          />
        </a-card>
      </a-spin>
    </div>

    <KnowledgeConfigForm v-model:open="editOpen" :current="kb" @saved="load" />

    <!-- 分块预览 -->
    <a-drawer v-model:open="chunksOpen" :title="chunkTarget?.filename || '分块预览'" placement="right" :width="620">
      <a-spin :spinning="chunksLoading">
        <EmptyState
          v-if="!chunks.length"
          :icon="BlockOutlined"
          title="暂无分块"
          description="文档可能还在处理中，或处理失败。"
        />
        <div v-for="chunk in chunks" :key="chunk.id" class="chunk-item">
          <div class="chunk-item__head">
            <a-tag class="tag-mono">#{{ chunk.chunk_index }}</a-tag>
            <span class="chunk-item__tokens">约 {{ chunk.token_count }} tokens</span>
          </div>
          <p class="chunk-item__content">{{ chunk.content }}</p>
        </div>
      </a-spin>
    </a-drawer>

    <!-- 检索测试 -->
    <a-modal v-model:open="testOpen" title="检索测试" :footer="null" :width="720">
      <a-input-search
        v-model:value="testQuery"
        placeholder="输入问题，验证召回效果"
        enter-button="检索"
        :loading="testing"
        @search="runTest"
      />
      <a-spin :spinning="testing">
        <div v-if="testResult" class="test-list">
          <p class="test-hint">
            命中 {{ testResult.chunks.length }} 条 · 耗时 {{ formatDuration(testResult.latency_ms) }}
          </p>
          <div v-for="(chunk, index) in testResult.chunks" :key="index" class="test-item">
            <div class="test-item__head">
              <a-tag class="tag-mono">{{ index + 1 }}</a-tag>
              <span class="text-ellipsis">{{ chunk.filename }}</span>
              <a-tag class="test-item__score">相似度 {{ (chunk.score ?? 0).toFixed(4) }}</a-tag>
            </div>
            <p class="test-item__content">{{ chunk.content }}</p>
          </div>
        </div>
      </a-spin>
    </a-modal>
  </AdminLayout>
</template>

<script setup lang="ts">
/** 知识库详情：基本信息 / Embedding / Chunk / Retriever 配置 + 文档列表 + 检索测试 */
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import {
  BlockOutlined,
  ArrowLeftOutlined,
  ExperimentOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import { useRoute, useRouter } from 'vue-router'

import EmptyState from '@/components/common/EmptyState.vue'
import DocumentList from '@/components/knowledge/DocumentList.vue'
import KnowledgeConfigForm from '@/components/knowledge/KnowledgeConfigForm.vue'
import AdminLayout from '@/layouts/AdminLayout.vue'
import { documentApi, knowledgeApi } from '@/api/knowledge'
import type { DocumentChunkItem, DocumentItem, KnowledgeBase, RetrievalTestResult } from '@/types'
import { formatDateTime, formatDuration } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const kbId = Number(route.params.id)

const kb = ref<(KnowledgeBase & { documents?: DocumentItem[] }) | null>(null)
const documents = ref<DocumentItem[]>([])
const loading = ref(false)
const documentsLoading = ref(false)
const uploading = ref(false)
const uploadPercent = ref(0)
const editOpen = ref(false)
const chunksOpen = ref(false)
const chunksLoading = ref(false)
const chunks = ref<DocumentChunkItem[]>([])
const chunkTarget = ref<DocumentItem | null>(null)
const testOpen = ref(false)
const testQuery = ref('')
const testing = ref(false)
const testResult = ref<RetrievalTestResult | null>(null)
const checking = ref(false)
const limits = ref({ max_upload_size_mb: 50, allowed_extensions: ['.pdf', '.docx', '.txt', '.md', '.csv', '.xlsx'] })

let stopPolling: (() => void) | null = null

async function load() {
  loading.value = true
  try {
    kb.value = await knowledgeApi.get(kbId)
    documents.value = kb.value.documents || []
    await loadDocuments()
    startPolling()
  } finally {
    loading.value = false
  }
}

async function loadDocuments() {
  documentsLoading.value = true
  try {
    documents.value = await documentApi.listByKb(kbId, { page_size: 100 }).then((data) => data.items)
  } finally {
    documentsLoading.value = false
  }
}

function startPolling() {
  stopPolling?.()
  const processing = documents.value.some((item) =>
    ['pending', 'parsing', 'splitting', 'embedding'].includes(item.status),
  )
  if (!processing) return
  const timer = window.setInterval(async () => {
    await loadDocuments()
    if (!documents.value.some((item) => ['pending', 'parsing', 'splitting', 'embedding'].includes(item.status))) {
      window.clearInterval(timer)
      const detail = await knowledgeApi.get(kbId)
      kb.value = detail
    }
  }, 2500)
  stopPolling = () => window.clearInterval(timer)
}

async function handleUpload(files: File[]) {
  if (!files.length) return
  uploading.value = true
  uploadPercent.value = 0
  try {
    for (const file of files) {
      await documentApi.upload(kbId, file, (percent) => (uploadPercent.value = percent))
      message.success(`${file.name} 上传成功，正在后台解析`)
    }
    await loadDocuments()
    startPolling()
  } finally {
    uploading.value = false
    uploadPercent.value = 0
  }
}

async function handleDelete(document: DocumentItem) {
  await documentApi.remove(document.id)
  message.success('文档已删除')
  await loadDocuments()
  const detail = await knowledgeApi.get(kbId)
  kb.value = detail
}

async function handleReindex(document: DocumentItem) {
  await documentApi.reindex(document.id)
  message.success('已加入重新向量化队列')
  await loadDocuments()
  startPolling()
}

async function openChunks(document: DocumentItem) {
  chunkTarget.value = document
  chunksOpen.value = true
  chunksLoading.value = true
  try {
    const data = await documentApi.chunks(document.id, { page_size: 50 })
    chunks.value = data.items
  } finally {
    chunksLoading.value = false
  }
}

function openEdit() {
  editOpen.value = true
}

function openTest() {
  testQuery.value = ''
  testResult.value = null
  testOpen.value = true
}

async function runTest() {
  if (!testQuery.value.trim()) {
    message.warning('请输入检索内容')
    return
  }
  testing.value = true
  try {
    testResult.value = await knowledgeApi.retrievalTest(kbId, { query: testQuery.value.trim() })
  } finally {
    testing.value = false
  }
}

async function checkEmbedding() {
  checking.value = true
  try {
    const result = await knowledgeApi.embeddingCheck(kbId)
    message.success(`配置可用：${result.provider}:${result.model}（${result.dimension} 维）`)
  } finally {
    checking.value = false
  }
}

onMounted(async () => {
  limits.value = await documentApi.limits().catch(() => limits.value)
  await load()
})

onBeforeUnmount(() => stopPolling?.())
</script>

<style scoped>
.kb-detail__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 14px;
  margin-bottom: 16px;
}

.kb-detail__documents {
  margin-bottom: 24px;
}

.chunk-item {
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  margin-bottom: 8px;
}

.chunk-item__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.chunk-item__tokens {
  font-size: 12px;
  color: var(--text-secondary);
}

.chunk-item__content {
  margin: 0;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-secondary);
  white-space: pre-wrap;
}

.test-hint {
  margin-top: 14px;
  font-size: 12px;
  color: var(--text-secondary);
}

.test-item {
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  margin-bottom: 8px;
}

.test-item__head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.test-item__score {
  margin-left: auto;
  margin-inline-end: 0;
  font-size: 11px;
}

.test-item__content {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-secondary);
  max-height: 160px;
  overflow: auto;
  white-space: pre-wrap;
}
</style>
