<template>
  <div class="empty-state">
    <div class="empty-state__icon">
      <component :is="icon" />
    </div>
    <h4 class="empty-state__title">{{ title }}</h4>
    <p v-if="description" class="empty-state__desc">{{ description }}</p>
    <div v-if="$slots.default" class="empty-state__action">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 空状态组件
 * 统一使用 Ant Design 图标（不使用 emoji），保持与全站视觉一致。
 * 配色：仅用灰白，靠「留白 + 发丝边」营造秩序感，不引入强调色。
 */
import type { Component } from 'vue'

withDefaults(
  defineProps<{
    title: string
    /** 图标组件，例如 MessageOutlined / FileTextOutlined */
    icon: Component
    description?: string
  }>(),
  { description: '' },
)
</script>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 48px 20px;
  text-align: center;
}

.empty-state__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  margin-bottom: 6px;
  border-radius: 16px;
  background: var(--bg-sunken);
  border: 1px solid var(--border-color);
  color: var(--text-secondary);
  font-size: 22px;
}

.empty-state__title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.empty-state__desc {
  margin: 0;
  max-width: 380px;
  font-size: 13px;
  color: var(--text-secondary);
}

.empty-state__action {
  margin-top: 8px;
}
</style>
