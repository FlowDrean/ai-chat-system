<template>
  <a-select
    :value="modelValue ?? undefined"
    :options="options"
    :loading="loading"
    show-search
    option-filter-prop="label"
    allow-clear
    :placeholder="placeholder"
    :style="{ width }"
    :size="size"
    @change="handleChange"
  >
    <template #option="option">
      <div class="prompt-option">
        <span class="text-ellipsis">{{ option.label }}</span>
        <a-tag v-if="option.builtin" class="prompt-option__tag">内置</a-tag>
      </div>
    </template>
  </a-select>
</template>

<script setup lang="ts">
/** Prompt 选择器 */
import { computed, onMounted, ref } from 'vue'

import { promptApi } from '@/api/prompt'
import type { PromptItem } from '@/types'

const props = withDefaults(
  defineProps<{
    modelValue?: number | null
    width?: string
    size?: 'small' | 'middle' | 'large'
    placeholder?: string
  }>(),
  { width: '180px', size: 'middle', placeholder: '默认 System Prompt' },
)

const emit = defineEmits<{
  (event: 'update:modelValue', value: number | null): void
  (event: 'change', value: number | null, prompt?: PromptItem): void
}>()

const prompts = ref<PromptItem[]>([])
const loading = ref(false)

const options = computed(() =>
  prompts.value
    .filter((item) => item.enabled)
    .map((item) => ({ value: item.id, label: item.name, builtin: item.is_builtin })),
)

onMounted(async () => {
  loading.value = true
  try {
    const data = await promptApi.list({ page_size: 100 })
    prompts.value = data.items
  } finally {
    loading.value = false
  }
})

function handleChange(value: unknown) {
  const id = (value as number | undefined) ?? null
  emit('update:modelValue', id)
  emit('change', id, prompts.value.find((item) => item.id === id))
}
</script>

<style scoped>
.prompt-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.prompt-option__tag {
  font-size: 11px;
  margin-inline-end: 0;
}
</style>
