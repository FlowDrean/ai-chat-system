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
      <div class="kb-option">
        <span class="text-ellipsis">{{ option.label }}</span>
        <span class="kb-option__count">{{ option.count }} chunks</span>
      </div>
    </template>
  </a-select>
</template>

<script setup lang="ts">
/** 知识库选择器 */
import { computed, onMounted } from 'vue'

import { useKnowledgeStore } from '@/stores/knowledge'

const props = withDefaults(
  defineProps<{
    modelValue?: number | null
    width?: string
    size?: 'small' | 'middle' | 'large'
    placeholder?: string
  }>(),
  { width: '190px', size: 'middle', placeholder: '不使用知识库' },
)

const emit = defineEmits<{
  (event: 'update:modelValue', value: number | null): void
  (event: 'change', value: number | null): void
}>()

const store = useKnowledgeStore()

const options = computed(() =>
  store.knowledgeBases.map((kb) => ({
    value: kb.id,
    label: kb.name,
    count: kb.chunk_count,
  })),
)
const loading = computed(() => store.loading)

onMounted(() => {
  store.fetchKnowledgeBases().catch(() => undefined)
})

function handleChange(value: unknown) {
  const id = (value as number | undefined) ?? null
  emit('update:modelValue', id)
  emit('change', id)
}
</script>

<style scoped>
.kb-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.kb-option__count {
  font-size: 12px;
  color: var(--text-secondary);
}
</style>
