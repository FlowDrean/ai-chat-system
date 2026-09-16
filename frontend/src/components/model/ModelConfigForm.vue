<template>
  <a-modal
    :open="open"
    :title="isEdit ? '编辑模型' : '新增模型'"
    :width="720"
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
          <a-form-item label="模型名称" name="name" extra="用于在界面上区分，例如「DeepSeek Chat」">
            <a-input v-model:value="form.name" placeholder="请输入模型名称" :maxlength="60" />
          </a-form-item>
        </a-col>
        <a-col :xs="24" :md="12">
          <a-form-item label="模型供应商" name="provider" extra="新增供应商只需在后端 LLM Factory 注册">
            <a-select v-model:value="form.provider" :options="providerOptions" @change="handleProviderChange" />
          </a-form-item>
        </a-col>

        <a-col :xs="24" :md="12">
          <a-form-item label="模型 ID" name="model_name" extra="例如 deepseek-chat / gpt-4o-mini / qwen2.5:7b">
            <a-input v-model:value="form.model_name" placeholder="请输入模型 ID" />
          </a-form-item>
        </a-col>
        <a-col :xs="24" :md="12">
          <a-form-item label="Base URL" name="base_url">
            <a-input v-model:value="form.base_url" placeholder="留空使用供应商默认地址" allow-clear />
          </a-form-item>
        </a-col>

        <a-col :xs="24" :md="12">
          <a-form-item label="API Key" name="api_key">
            <a-input-password
              v-model:value="form.api_key"
              :placeholder="isEdit && current?.has_api_key ? `已配置：${current.api_key_masked}（留空则不修改）` : '请输入 API Key'"
              autocomplete="new-password"
            />
            <p class="form-tip">API Key 在后端加密存储，接口只返回脱敏值，日志不会记录明文。</p>
          </a-form-item>
        </a-col>
        <a-col :xs="24" :md="12">
          <a-form-item label="状态">
            <div class="switch-row">
              <a-switch v-model:checked="form.enabled" checked-children="启用" un-checked-children="禁用" />
              <a-switch
                v-model:checked="form.is_default"
                checked-children="默认"
                un-checked-children="非默认"
              />
            </div>
          </a-form-item>
        </a-col>

        <a-col :xs="12" :md="6">
          <a-form-item label="Temperature">
            <a-input-number v-model:value="form.temperature" :min="0" :max="2" :step="0.1" style="width: 100%" />
          </a-form-item>
        </a-col>
        <a-col :xs="12" :md="6">
          <a-form-item label="Top P">
            <a-input-number v-model:value="form.top_p" :min="0" :max="1" :step="0.05" style="width: 100%" />
          </a-form-item>
        </a-col>
        <a-col :xs="12" :md="6">
          <a-form-item label="Max Tokens">
            <a-input-number v-model:value="form.max_tokens" :min="1" :max="131072" :step="256" style="width: 100%" />
          </a-form-item>
        </a-col>
        <a-col :xs="12" :md="6">
          <a-form-item label="频率惩罚">
            <a-input-number v-model:value="form.frequency_penalty" :min="-2" :max="2" :step="0.1" style="width: 100%" />
          </a-form-item>
        </a-col>

        <a-col :span="24">
          <a-form-item label="备注">
            <a-textarea v-model:value="form.description" :rows="2" :maxlength="200" placeholder="可选，便于团队协作" />
          </a-form-item>
        </a-col>
      </a-row>

      <a-alert
        v-if="providerHint"
        type="info"
        show-icon
        :message="providerHint"
        class="provider-hint"
      />
    </a-form>
  </a-modal>
</template>

<script setup lang="ts">
/** 模型配置表单（Modal）—— 新增 / 编辑 */
import { computed, reactive, ref, watch } from 'vue'
import type { FormInstance } from 'ant-design-vue'
import type { Rule } from 'ant-design-vue/es/form'
import { message } from 'ant-design-vue'

import { useModelStore } from '@/stores/model'
import type { ModelItem, ModelPayload, ProviderValue } from '@/types'

const props = defineProps<{
  open: boolean
  current?: ModelItem | null
}>()

const emit = defineEmits<{
  (event: 'update:open', value: boolean): void
  (event: 'saved'): void
}>()

const modelStore = useModelStore()
const formRef = ref<FormInstance>()
const submitting = ref(false)

const isEdit = computed(() => Boolean(props.current?.id))

function emptyForm(): ModelPayload {
  return {
    name: '',
    provider: 'deepseek',
    model_name: '',
    base_url: null,
    api_key: '',
    temperature: 0.7,
    top_p: 1,
    max_tokens: 4096,
    frequency_penalty: 0,
    presence_penalty: 0,
    enabled: true,
    is_default: false,
    supports_stream: true,
    supports_vision: false,
    description: '',
  }
}

const form = reactive<ModelPayload>(emptyForm())

const rules: Record<string, Rule[]> = {
  name: [{ required: true, message: '请输入模型名称', trigger: 'blur' }],
  provider: [{ required: true, message: '请选择供应商', trigger: 'change' }],
  model_name: [{ required: true, message: '请输入模型 ID', trigger: 'blur' }],
}

const providerOptions = computed(() =>
  modelStore.providers.map((item) => ({ value: item.value, label: item.label })),
)

const providerHint = computed(() => {
  const info = modelStore.providers.find((item) => item.value === form.provider)
  if (!info) return ''
  const parts = [info.description || '']
  if (info.default_base_url) parts.push(`默认地址：${info.default_base_url}`)
  return parts.filter(Boolean).join('　|　')
})

watch(
  () => props.open,
  (open) => {
    if (!open) return
    modelStore.fetchProviders().catch(() => undefined)
    const current = props.current
    if (current) {
      Object.assign(form, {
        name: current.name,
        provider: current.provider,
        model_name: current.model_name,
        base_url: current.base_url,
        api_key: '',
        temperature: current.temperature,
        top_p: current.top_p,
        max_tokens: current.max_tokens,
        frequency_penalty: current.frequency_penalty,
        presence_penalty: current.presence_penalty,
        enabled: current.enabled,
        is_default: current.is_default,
        supports_stream: current.supports_stream,
        supports_vision: current.supports_vision,
        description: current.description || '',
      })
    } else {
      Object.assign(form, emptyForm())
      if (modelStore.defaultModel) {
        form.provider = modelStore.defaultModel.provider
      }
    }
  },
)

function handleProviderChange(value: ProviderValue) {
  const info = modelStore.providers.find((item) => item.value === value)
  if (info?.default_base_url && !props.current) {
    form.base_url = info.default_base_url
  }
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
  submitting.value = true
  try {
    const payload: Partial<ModelPayload> = { ...form }
    if (!payload.api_key) delete payload.api_key
    if (isEdit.value && props.current) {
      await modelStore.updateModel(props.current.id, payload)
      message.success('模型已更新')
    } else {
      await modelStore.createModel(payload as ModelPayload)
      message.success('模型已创建')
    }
    emit('saved')
    close()
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.form-tip {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.switch-row {
  display: flex;
  align-items: center;
  gap: 16px;
  height: 32px;
}

.provider-hint {
  margin-top: 4px;
}
</style>
