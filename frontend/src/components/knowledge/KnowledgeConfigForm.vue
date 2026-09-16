<template>
  <a-modal
    :open="open"
    :title="isEdit ? '编辑知识库' : '新建知识库'"
    :width="760"
    :confirm-loading="submitting"
    ok-text="保存"
    cancel-text="取消"
    destroy-on-close
    @ok="submit"
    @cancel="close"
  >
    <a-form ref="formRef" :model="form" :rules="rules" layout="vertical">
      <a-row :gutter="16">
        <a-col :xs="24" :md="12">
          <a-form-item label="知识库名称" name="name">
            <a-input v-model:value="form.name" placeholder="例如：产品说明书" :maxlength="60" />
          </a-form-item>
        </a-col>
        <a-col :xs="24" :md="12">
          <a-form-item label="描述">
            <a-input v-model:value="form.description" placeholder="可选" :maxlength="200" />
          </a-form-item>
        </a-col>

        <a-col :span="24">
          <a-divider orientation="left" class="form-divider">Embedding 配置</a-divider>
        </a-col>

        <a-col :xs="24" :md="12">
          <a-form-item label="Embedding 供应商" name="embedding_provider">
            <a-select
              v-model:value="form.embedding_provider"
              :options="providerOptions"
              @change="handleProviderChange"
            />
          </a-form-item>
        </a-col>
        <a-col :xs="24" :md="12">
          <a-form-item label="Embedding 模型" name="embedding_model">
            <a-select
              v-model:value="form.embedding_model"
              :options="modelOptions"
              :dropdown-match-select-width="false"
              show-search
              @change="handleModelChange"
            />
          </a-form-item>
        </a-col>

        <a-col v-if="needsApiKey" :xs="24" :md="12">
          <a-form-item label="Embedding API Key">
            <a-input-password
              v-model:value="form.embedding_api_key"
              :placeholder="isEdit && current?.has_embedding_api_key ? `已配置：${current.embedding_api_key_masked}（留空不修改）` : '请输入 API Key'"
              autocomplete="new-password"
            />
          </a-form-item>
        </a-col>
        <a-col :xs="24" :md="12">
          <a-form-item label="Base URL">
            <a-input v-model:value="form.embedding_base_url" placeholder="留空使用默认地址" allow-clear />
          </a-form-item>
        </a-col>

        <a-col :span="24">
          <a-divider orientation="left" class="form-divider">切分与检索</a-divider>
        </a-col>

        <a-col :xs="12" :md="6">
          <a-form-item label="Chunk Size">
            <a-input-number v-model:value="form.chunk_size" :min="100" :max="8000" :step="100" style="width: 100%" />
          </a-form-item>
        </a-col>
        <a-col :xs="12" :md="6">
          <a-form-item label="Chunk Overlap">
            <a-input-number v-model:value="form.chunk_overlap" :min="0" :max="2000" :step="20" style="width: 100%" />
          </a-form-item>
        </a-col>
        <a-col :xs="12" :md="6">
          <a-form-item label="Top K">
            <a-input-number v-model:value="form.top_k" :min="1" :max="50" style="width: 100%" />
          </a-form-item>
        </a-col>
        <a-col :xs="12" :md="6">
          <a-form-item label="相似度阈值">
            <a-input-number
              v-model:value="form.similarity_threshold"
              :min="-1"
              :max="1"
              :step="0.05"
              style="width: 100%"
            />
          </a-form-item>
        </a-col>

        <a-col :span="24">
          <a-form-item>
            <div class="switch-row">
              <a-switch v-model:checked="form.rerank_enabled" />
              <span>启用轻量 ReRank（向量相似度 + 词法重合度加权）</span>
            </div>
          </a-form-item>
        </a-col>
      </a-row>

      <a-alert type="info" show-icon :message="embeddingHint" class="embedding-hint" />
    </a-form>
  </a-modal>
</template>

<script setup lang="ts">
/**
 * 知识库配置表单
 * 包含：基本信息 / Embedding 配置 / Chunk 配置 / Retriever 配置
 */
import { computed, reactive, ref, watch } from 'vue'
import type { FormInstance } from 'ant-design-vue'
import type { Rule } from 'ant-design-vue/es/form'
import { message } from 'ant-design-vue'

import { useKnowledgeStore } from '@/stores/knowledge'
import type { KnowledgeBase, KnowledgeBasePayload } from '@/types'

const props = defineProps<{
  open: boolean
  current?: KnowledgeBase | null
}>()

const emit = defineEmits<{
  (event: 'update:open', value: boolean): void
  (event: 'saved'): void
}>()

const store = useKnowledgeStore()
const formRef = ref<FormInstance>()
const submitting = ref(false)

const isEdit = computed(() => Boolean(props.current?.id))

function emptyForm(): KnowledgeBasePayload & { embedding_api_key?: string | null } {
  return {
    name: '',
    description: '',
    embedding_provider: 'local',
    embedding_model: 'local-hash-512',
    embedding_base_url: null,
    embedding_api_key: '',
    embedding_dimension: 512,
    chunk_size: 800,
    chunk_overlap: 120,
    top_k: 4,
    similarity_threshold: 0.2,
    rerank_enabled: false,
  }
}

const form = reactive(emptyForm())

const rules: Record<string, Rule[]> = {
  name: [{ required: true, message: '请输入知识库名称', trigger: 'blur' }],
  embedding_provider: [{ required: true, message: '请选择 Embedding 供应商', trigger: 'change' }],
  embedding_model: [{ required: true, message: '请选择 embedding 模型', trigger: 'change' }],
}

const providerOptions = computed(() =>
  store.embeddingProviders.map((item) => ({ value: item.value, label: item.label })),
)

const currentProvider = computed(() =>
  store.embeddingProviders.find((item) => item.value === form.embedding_provider),
)

const modelOptions = computed(() =>
  (currentProvider.value?.presets || []).map((item) => ({
    value: item.value,
    label: `${item.label}（${item.dimension} 维）`,
  })),
)

const needsApiKey = computed(() => form.embedding_provider !== 'local' && form.embedding_provider !== 'ollama')

const embeddingHint = computed(() => {
  if (form.embedding_provider === 'local') {
    return '本地轻量向量：无需 API Key，完全离线可用，适合开发调试与关键词型检索；需要更强的语义召回时请切换为 openai / qwen / ollama 等真实 Embedding。'
  }
  if (form.embedding_provider === 'ollama') {
    return 'Ollama 本地服务：请确保已运行 ollama serve 并拉取对应 embedding 模型（如 ollama pull bge-m3）。'
  }
  return '更换 Embedding 模型后，已有文档需要在文档列表中点击「重新向量化」才会生效。'
})

watch(
  () => props.open,
  async (open) => {
    if (!open) return
    await store.fetchEmbeddingProviders().catch(() => undefined)
    if (props.current) {
      const current = props.current
      Object.assign(form, {
        name: current.name,
        description: current.description || '',
        embedding_provider: current.embedding_provider,
        embedding_model: current.embedding_model,
        embedding_base_url: current.embedding_base_url,
        embedding_api_key: '',
        embedding_dimension: current.embedding_dimension,
        chunk_size: current.chunk_size,
        chunk_overlap: current.chunk_overlap,
        top_k: current.top_k,
        similarity_threshold: current.similarity_threshold,
        rerank_enabled: current.rerank_enabled,
      })
    } else {
      Object.assign(form, emptyForm())
    }
  },
)

function handleProviderChange() {
  const provider = currentProvider.value
  const first = provider?.presets?.[0]
  if (first) {
    form.embedding_model = first.value
    form.embedding_dimension = first.dimension
  }
  form.embedding_base_url = provider?.default_base_url || null
}

function handleModelChange(value: string) {
  const preset = currentProvider.value?.presets?.find((item) => item.value === value)
  if (preset) form.embedding_dimension = preset.dimension
}

function close() {
  emit('update:open', false)
}

async function submit() {
  try {
    await formRef.value?.validate()
  } catch {
    return
  }
  if (form.chunk_overlap >= form.chunk_size) {
    message.error('Chunk Overlap 必须小于 Chunk Size')
    return
  }
  submitting.value = true
  try {
    const payload: Partial<KnowledgeBasePayload> = { ...form }
    if (!payload.embedding_api_key) delete payload.embedding_api_key
    if (isEdit.value && props.current) {
      await store.updateKnowledgeBase(props.current.id, payload)
      message.success('知识库已更新')
    } else {
      await store.createKnowledgeBase(payload as KnowledgeBasePayload)
      message.success('知识库已创建')
    }
    emit('saved')
    close()
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.form-divider {
  margin: 4px 0 16px;
  font-size: 13px;
  color: var(--text-secondary);
}

.switch-row {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: var(--text-secondary);
}

.embedding-hint {
  margin-top: 4px;
}
</style>
