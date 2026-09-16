<template>
  <div class="loading-view" :style="{ minHeight }">
    <a-spin :size="size" />
    <span v-if="text" class="loading-view__text">{{ text }}</span>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    text?: string
    size?: 'small' | 'default' | 'large'
    minHeight?: string
  }>(),
  {
    text: '加载中',
    size: 'default',
    minHeight: '160px',
  },
)
</script>

<style scoped>
.loading-view {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  width: 100%;
}

.loading-view__text {
  font-size: 13px;
  color: var(--text-secondary);
}
</style>
