<template>
  <AdminLayout>
    <div class="page-container">
      <div class="page-header">
        <div>
          <h1 class="page-title">模型管理</h1>
          <p class="page-subtitle">
            统一配置多个大模型供应商，支持测试连接、设为默认、启用 / 禁用。API Key 加密存储且全程脱敏。
          </p>
        </div>
        <a-space>
          <a-button @click="refresh">
            <template #icon><ReloadOutlined /></template>
            刷新
          </a-button>
          <a-button type="primary" @click="openCreate">
            <template #icon><PlusOutlined /></template>
            新增模型
          </a-button>
        </a-space>
      </div>

      <a-card :bordered="true" size="small">
        <div class="model-page__toolbar">
          <a-input
            v-model:value="filters.keyword"
            placeholder="搜索模型名称 / 模型 ID"
            allow-clear
            style="width: 240px"
            @press-enter="load"
          >
            <template #prefix><SearchOutlined /></template>
          </a-input>
          <a-select
            v-model:value="filters.provider"
            :options="providerOptions"
            placeholder="全部供应商"
            allow-clear
            style="width: 180px"
            @change="load"
          />
          <a-select
            v-model:value="filters.enabled"
            :options="[
              { value: true, label: '仅启用' },
              { value: false, label: '仅禁用' },
            ]"
            placeholder="全部状态"
            allow-clear
            style="width: 140px"
            @change="load"
          />
          <a-button type="primary" ghost @click="load">查询</a-button>
        </div>

        <LoadingView v-if="loading && !models.length" text="加载模型列表中…" />

        <EmptyState
          v-else-if="!models.length"
          :icon="DeploymentUnitOutlined"
          title="还没有配置模型"
          description="添加一个模型（如 DeepSeek、OpenAI 兼容接口或本地 Ollama），即可开始对话。"
        >
          <a-button type="primary" @click="openCreate">新增模型</a-button>
        </EmptyState>

        <a-table
          v-else
          :data-source="models"
          :columns="columns"
          :loading="loading"
          row-key="id"
          :pagination="paginationConfig"
          size="middle"
          @change="handleTableChange"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'name'">
              <div class="model-name">
                <span class="text-ellipsis">{{ record.name }}</span>
                <a-tag v-if="record.is_default" class="tag-mono model-name__tag">默认</a-tag>
              </div>
            </template>

            <template v-else-if="column.key === 'provider'">
              <a-tag :color="PROVIDER_COLORS[record.provider] || 'default'">
                {{ record.provider_label || record.provider }}
              </a-tag>
            </template>

            <template v-else-if="column.key === 'base_url'">
              <span class="text-secondary text-ellipsis" :title="record.base_url">
                {{ record.base_url || '默认地址' }}
              </span>
            </template>

            <template v-else-if="column.key === 'api_key'">
              <span class="mono text-secondary">{{ record.api_key_masked || '未配置' }}</span>
            </template>

            <template v-else-if="column.key === 'status'">
              <a-badge
                :status="record.status === 'ok' ? 'success' : record.status === 'error' ? 'error' : 'default'"
                :text="record.status === 'ok' ? '正常' : record.status === 'error' ? '异常' : '未测试'"
              />
            </template>

            <template v-else-if="column.key === 'enabled'">
              <a-switch
                :checked="record.enabled"
                size="small"
                @change="(checked: unknown) => handleToggle(record, Boolean(checked))"
              />
            </template>

            <template v-else-if="column.key === 'created_at'">
              {{ formatDateTime(record.created_at) }}
            </template>

            <template v-else-if="column.key === 'action'">
              <a-space :size="2">
                <a-tooltip title="测试连接">
                  <a-button size="small" type="text" :loading="testingId === record.id" @click="handleTest(record)">
                    <template #icon><ApiOutlined /></template>
                  </a-button>
                </a-tooltip>
                <a-tooltip title="设为默认">
                  <a-button
                    size="small"
                    type="text"
                    :disabled="record.is_default || !record.enabled"
                    @click="handleSetDefault(record)"
                  >
                    <template #icon><StarOutlined /></template>
                  </a-button>
                </a-tooltip>
                <a-tooltip title="复制配置">
                  <a-button size="small" type="text" @click="handleDuplicate(record)">
                    <template #icon><CopyOutlined /></template>
                  </a-button>
                </a-tooltip>
                <a-tooltip title="编辑">
                  <a-button size="small" type="text" @click="openEdit(record)">
                    <template #icon><EditOutlined /></template>
                  </a-button>
                </a-tooltip>
                <a-popconfirm
                  title="删除该模型？引用该模型的会话将失去绑定。"
                  ok-text="删除"
                  cancel-text="取消"
                  @confirm="handleDelete(record)"
                >
                  <a-button size="small" type="text" danger>
                    <template #icon><DeleteOutlined /></template>
                  </a-button>
                </a-popconfirm>
              </a-space>
            </template>
          </template>
        </a-table>

        <a-alert
          v-if="lastTestResult"
          class="model-page__result"
          :type="lastTestResult.success ? 'success' : 'error'"
          show-icon
          closable
          @close="lastTestResult = null"
          :message="`${lastTestResult.model_name || ''} ${lastTestResult.message}`"
          :description="
            lastTestResult.reply_preview
              ? `耗时 ${formatDuration(lastTestResult.latency_ms)} · 回复预览：${lastTestResult.reply_preview}`
              : `耗时 ${formatDuration(lastTestResult.latency_ms)}`
          "
        />
      </a-card>
    </div>

    <ModelConfigForm v-model:open="formOpen" :current="editing" @saved="load" />
  </AdminLayout>
</template>

<script setup lang="ts">
/** 模型管理页：表格 + Modal 表单 + 测试连接 / 默认模型 / 启停 */
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import type { TableColumnsType, TablePaginationConfig } from 'ant-design-vue'
import {
  DeploymentUnitOutlined,
  ApiOutlined,
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  StarOutlined,
} from '@ant-design/icons-vue'

import EmptyState from '@/components/common/EmptyState.vue'
import LoadingView from '@/components/common/LoadingView.vue'
import ModelConfigForm from '@/components/model/ModelConfigForm.vue'
import AdminLayout from '@/layouts/AdminLayout.vue'
import { useModelStore } from '@/stores/model'
import type { ModelItem } from '@/types'
import { PROVIDER_COLORS, formatDateTime, formatDuration } from '@/utils/format'

const modelStore = useModelStore()

const loading = ref(false)
const formOpen = ref(false)
const editing = ref<ModelItem | null>(null)
const testingId = ref<number | null>(null)
const lastTestResult = ref<Awaited<ReturnType<typeof modelStore.testModel>> | null>(null)
const total = ref(0)

const filters = reactive<{ keyword?: string; provider?: string; enabled?: boolean }>({
  keyword: undefined,
  provider: undefined,
  enabled: undefined,
})
const page = reactive({ current: 1, pageSize: 10 })

const models = computed(() => modelStore.models)
const providerOptions = computed(() =>
  modelStore.providers.map((item) => ({ value: item.value, label: item.label })),
)

const columns: TableColumnsType = [
  { title: '模型名称', key: 'name', dataIndex: 'name', width: 190 },
  { title: 'Provider', key: 'provider', width: 130 },
  { title: 'Model', key: 'model_name', dataIndex: 'model_name', ellipsis: true, width: 180 },
  { title: 'Base URL', key: 'base_url', ellipsis: true },
  { title: 'API Key', key: 'api_key', width: 150 },
  { title: '状态', key: 'status', width: 100 },
  { title: '启用', key: 'enabled', width: 80 },
  { title: '创建时间', key: 'created_at', width: 160 },
  { title: '操作', key: 'action', width: 210, fixed: 'right' },
]

const paginationConfig = computed<TablePaginationConfig>(() => ({
  current: page.current,
  pageSize: page.pageSize,
  total: total.value,
  showSizeChanger: true,
  showTotal: (value: number) => `共 ${value} 条`,
}))

async function load() {
  loading.value = true
  try {
    const data = await modelStore.fetchModels(true)
    total.value = data.length
  } finally {
    loading.value = false
  }
}

function refresh() {
  load()
}

function handleTableChange(pagination: TablePaginationConfig) {
  page.current = pagination.current || 1
  page.pageSize = pagination.pageSize || 10
}

function openCreate() {
  editing.value = null
  formOpen.value = true
}

function openEdit(record: ModelItem) {
  editing.value = record
  formOpen.value = true
}

async function handleTest(record: ModelItem) {
  testingId.value = record.id
  try {
    const result = await modelStore.testModel(record.id)
    lastTestResult.value = result
    if (result.success) message.success('模型连接正常')
    else message.error(result.message)
  } finally {
    testingId.value = null
  }
}

async function handleSetDefault(record: ModelItem) {
  await modelStore.setDefault(record.id)
  message.success(`已将「${record.name}」设为默认模型`)
}

async function handleToggle(record: ModelItem, enabled: boolean) {
  await modelStore.toggleModel(record.id, enabled)
  message.success(enabled ? '模型已启用' : '模型已禁用')
}

async function handleDuplicate(record: ModelItem) {
  await modelStore.duplicateModel(record.id)
  message.success('已复制模型配置')
}

async function handleDelete(record: ModelItem) {
  await modelStore.removeModel(record.id)
  message.success('模型已删除')
}

onMounted(async () => {
  await modelStore.fetchProviders().catch(() => undefined)
  await load()
})
</script>

<style scoped>
.model-page__toolbar {
  display: flex;
  gap: 10px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.model-name {
  display: flex;
  align-items: center;
  gap: 6px;
}

.model-name__tag {
  font-size: 11px;
  margin-inline-end: 0;
}

.model-page__result {
  margin-top: 14px;
}
</style>
