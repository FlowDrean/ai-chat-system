<template>
  <a-tooltip :title="tip" placement="bottom">
    <button type="button" class="theme-toggle" :aria-label="tip" @click="themeStore.toggle()">
      <svg class="theme-toggle__icon" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
        <!-- 当前是暗色 → 显示太阳（点击切回亮色） -->
        <g v-if="isDark">
          <circle cx="12" cy="12" r="4.3" fill="currentColor" />
          <g stroke="currentColor" stroke-width="1.7" stroke-linecap="round">
            <path d="M12 2.4v2.6M12 19v2.6M2.4 12H5M19 12h2.6" />
            <path d="M5.2 5.2 7 7M17 17l1.8 1.8M18.8 5.2 17 7M7 17l-1.8 1.8" />
          </g>
        </g>
        <!-- 当前是亮色 → 显示月亮（点击切到暗色） -->
        <path v-else d="M20.6 14.2A8.7 8.7 0 1 1 9.8 3.4a7 7 0 0 0 10.8 10.8Z" fill="currentColor" />
      </svg>
    </button>
  </a-tooltip>
</template>

<script setup lang="ts">
/**
 * 亮色 / 暗色切换按钮。
 *
 * 图标含义：显示「即将切换到」的模式 —— 亮色下显示月亮，暗色下显示太阳。
 * 自绘 svg 是因为 @ant-design/icons-vue 7 里没有 Moon/Sun 图标。
 */
import { computed } from 'vue'

import { useThemeStore } from '@/stores/theme'

const themeStore = useThemeStore()
const isDark = computed(() => themeStore.isDark)
const tip = computed(() => (isDark.value ? '切换到亮色模式' : '切换到暗色模式'))
</script>

<style scoped>
.theme-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background var(--transition), color var(--transition);
}

.theme-toggle:hover {
  background: var(--bg-hover);
  color: var(--brand);
}

.theme-toggle__icon {
  transition: transform 320ms cubic-bezier(0.4, 0, 0.2, 1);
}

.theme-toggle:hover .theme-toggle__icon {
  transform: rotate(28deg);
}

@media (prefers-reduced-motion: reduce) {
  .theme-toggle__icon,
  .theme-toggle:hover .theme-toggle__icon {
    transition: none;
    transform: none;
  }
}
</style>
