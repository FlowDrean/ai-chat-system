<template>
  <a-select
    :value="modelValue ?? undefined"
    :options="options"
    :loading="loading"
    :placeholder="placeholder"
    :style="{ width }"
    :size="size"
    :show-search="options.length > 8"
    option-filter-prop="label"
    allow-clear
    @change="handleChange"
  >
    <template #option="option">
      <div class="model-option">
        <span class="model-option__name text-ellipsis">{{ option.label }}</span>
        <span class="model-option__meta">{{ option.providerLabel }}</span>
      </div>
    </template>
  </a-select>
</template>

<script setup lang="ts">
/** 模型选择器（数据来自 modelStore，标记默认模型） */
import { computed, onMounted } from 'vue'

import { useModelStore } from '@/stores/model'

const props = withDefaults(
  defineProps<{
    modelValue?: number | null
    width?: string
    size?: 'small' | 'middle' | 'large'
    placeholder?: string
    onlyEnabled?: boolean
  }>(),
  { width: '200px', size: 'middle', placeholder: '选择模型', onlyEnabled: true },
)

const emit = defineEmits<{ (event: 'update:modelValue', value: number | null): void; (event: 'change', value: number | null): void }>()

const modelStore = useModelStore()

const loading = computed(() => modelStore.loading)

const options = computed(() =>
  (props.onlyEnabled ? modelStore.enabledModels : modelStore.models).map((model) => ({
    value: model.id,
    label: model.is_default ? `${model.name}（默认）` : model.name,
    providerLabel: model.provider_label,
  })),
)

onMounted(async () => {
  await Promise.all([modelStore.fetchModels(), modelStore.fetchProviders()])
  if (props.modelValue == null && modelStore.defaultModel) {
    emit('update:modelValue', modelStore.defaultModel.id)
  }
})

function handleChange(value: unknown) {
  const id = (value as number | undefined) ?? null
  emit('update:modelValue', id)
  emit('change', id)
}
</script>

<style scoped>
.model-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.model-option__meta {
  font-size: 12px;
  color: var(--text-secondary);
}
</style>
