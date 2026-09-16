<template>
  <div class="stat-card">
    <div class="stat-card__head">
      <span class="stat-card__label">{{ label }}</span>
      <span class="stat-card__icon">
        <component :is="icon" v-if="icon" />
      </span>
    </div>
    <div class="stat-card__value">{{ value }}</div>
    <div v-if="hint" class="stat-card__hint">{{ hint }}</div>
  </div>
</template>

<script setup lang="ts">
import type { Component } from 'vue'

defineProps<{
  label: string
  value: string | number
  hint?: string
  icon?: Component
}>()
</script>

<style scoped>
.stat-card {
  padding: 16px 18px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  transition: box-shadow var(--transition), border-color var(--transition);
}

.stat-card:hover {
  border-color: var(--border-dark);
  box-shadow: var(--shadow-pop);
}

.stat-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.stat-card__label {
  font-size: 13px;
  color: var(--text-secondary);
}

/* 图标片：统一灰白底 + 发丝边，不引入任何强调色 */
.stat-card__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: var(--bg-sunken);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  font-size: 14px;
  flex-shrink: 0;
}

.stat-card__value {
  margin-top: 10px;
  font-size: 26px;
  font-weight: 600;
  line-height: 1.2;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}

.stat-card__hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}
</style>
