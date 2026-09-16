<template>
  <AdminLayout>
    <div class="page-container">
      <div class="page-header">
        <div>
          <h1 class="page-title">知识库</h1>
          <p class="page-subtitle">
            创建知识库、上传文档并配置 Embedding / 切分 / 召回参数，让 AI 基于你的专属资料回答。
          </p>
        </div>
        <a-space>
          <a-input
            v-model:value="keyword"
            placeholder="搜索知识库"
            allow-clear
            style="width: 200px"
            @press-enter="load"
          >
            <template #prefix><SearchOutlined /></template>
          </a-input>
          <a-button @click="load">
            <template #icon><ReloadOutlined /></template>
          </a-button>
          <a-button type="primary" @click="openCreate">
            <template #icon><PlusOutlined /></template>
            新建知识库
          </a-button>
        </a-space>
      </div>

      <div class="knowledge-page__overview">
        <StatCard label="知识库" :value="store.knowledgeBases.length" :icon="DatabaseOutlined" />
        <StatCard label="文档总数" :value="store.totalDocuments" :icon="FileTextOutlined" />
        <StatCard label="向量分块" :value="store.totalChunks" :icon="BlockOutlined" />
      </div>

      <LoadingView v-if="store.loading && !store.knowledgeBases.length" text="加载知识库中…" />

      <EmptyState
        v-else-if="!store.knowledgeBases.length"
        :icon="DatabaseOutlined"
        title="还没有知识库"
        description="创建一个知识库，让 AI 学习你的专属资料。"
      >
        <a-button type="primary" @click="openCreate">创建知识库</a-button>
      </EmptyState>

      <div v-else class="knowledge-page__grid">
        <KnowledgeCard
          v-for="kb in store.knowledgeBases"
          :key="kb.id"
          :kb="kb"
          @open="openDetail"
          @edit="openEdit"
          @test="openTest"
          @delete="handleDelete"
        />
      </div>
    </div>

    <KnowledgeConfigForm v-model:open="formOpen" :current="editing" @saved="load" />

    <!-- 检索测试 -->
    <a-modal v-model:open="testOpen" title="检索测试" :footer="null" :width="720">
      <p class="test-hint">
        检索测试只做「Query Embedding → 向量检索」，不会调用大模型，用于验证文档是否已正确向量化。
      </p>
      <a-input-search
        v-model:value="testQuery"
        placeholder="输入一个与知识库内容相关的问题"
        enter-button="开始检索"
        :loading="testing"
        @search="runTest"
      />
      <a-spin :spinning="testing">
        <div v-if="testResult" class="test-result">
          <p class="test-result__meta">
            命中 {{ testResult.chunks.length }} 条 · 耗时 {{ formatDuration(testResult.latency_ms) }}
          </p>
          <div v-for="(chunk, index) in testResult.chunks" :key="index" class="test-result__item">
            <div class="test-result__head">
              <a-tag class="tag-mono">{{ index + 1 }}</a-tag>
              <span class="text-ellipsis">{{ chunk.filename }}</span>
              <span v-if="chunk.page" class="test-result__page">第 {{ chunk.page }} 页</span>
              <a-tag class="test-result__score">相似度 {{ (chunk.score ?? 0).toFixed(4) }}</a-tag>
            </div>
            <p class="test-result__content">{{ chunk.content }}</p>
          </div>
          <EmptyState
            v-if="!testResult.chunks.length"
            :icon="SearchOutlined"
            title="没有检索到内容"
            description="可以尝试降低相似度阈值、提高 Top K，或点击文档列表中的「重新向量化」。"
          />
        </div>
      </a-spin>
    </a-modal>
  </AdminLayout>
</template>

<script setup lang="ts">
/** 知识库管理页：Card 网格 + 新建/编辑 + 检索测试 */
import { onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import {
  BlockOutlined,
  DatabaseOutlined,
  FileTextOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue'
import { useRouter } from 'vue-router'

import EmptyState from '@/components/common/EmptyState.vue'
import LoadingView from '@/components/common/LoadingView.vue'
import StatCard from '@/components/common/StatCard.vue'
import KnowledgeCard from '@/components/knowledge/KnowledgeCard.vue'
import KnowledgeConfigForm from '@/components/knowledge/KnowledgeConfigForm.vue'
import AdminLayout from '@/layouts/AdminLayout.vue'
import { knowledgeApi } from '@/api/knowledge'
import { useKnowledgeStore } from '@/stores/knowledge'
import type { KnowledgeBase, RetrievalTestResult } from '@/types'
import { formatDuration } from '@/utils/format'

const router = useRouter()
const store = useKnowledgeStore()

const keyword = ref('')
const formOpen = ref(false)
const editing = ref<KnowledgeBase | null>(null)
const testOpen = ref(false)
const testQuery = ref('')
const testing = ref(false)
const testResult = ref<RetrievalTestResult | null>(null)
const testTarget = ref<KnowledgeBase | null>(null)

async function load() {
  await store.fetchKnowledgeBases(true).catch(() => undefined)
}

function openCreate() {
  editing.value = null
  formOpen.value = true
}

function openEdit(kb: KnowledgeBase) {
  editing.value = kb
  formOpen.value = true
}

function openDetail(kb: KnowledgeBase) {
  router.push(`/admin/knowledge/${kb.id}`)
}

function openTest(kb: KnowledgeBase) {
  testTarget.value = kb
  testQuery.value = ''
  testResult.value = null
  testOpen.value = true
}

async function runTest() {
  if (!testTarget.value || !testQuery.value.trim()) {
    message.warning('请输入检索内容')
    return
  }
  testing.value = true
  try {
    testResult.value = await knowledgeApi.retrievalTest(testTarget.value.id, {
      query: testQuery.value.trim(),
      top_k: testTarget.value.top_k,
    })
  } finally {
    testing.value = false
  }
}

async function handleDelete(kb: KnowledgeBase) {
  await store.removeKnowledgeBase(kb.id)
  message.success('知识库已删除')
}

onMounted(load)
</script>

<style scoped>
.knowledge-page__overview {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 14px;
  margin-bottom: 20px;
}

.knowledge-page__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 14px;
}

.test-hint {
  font-size: 12px;
  color: var(--text-secondary);
}

.test-result {
  margin-top: 16px;
}

.test-result__meta {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 10px;
}

.test-result__item {
  padding: 10px 12px;
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  margin-bottom: 8px;
}

.test-result__head {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.test-result__page {
  color: var(--text-secondary);
  font-size: 12px;
}

.test-result__score {
  margin-left: auto;
  margin-inline-end: 0;
  font-size: 11px;
}

.test-result__content {
  margin: 8px 0 0;
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-secondary);
  max-height: 160px;
  overflow: auto;
  white-space: pre-wrap;
}
</style>
