/**
 * 主题（亮色 / 暗色）状态。
 *
 * 设计：
 *  - mode 是「用户的选择」：light / dark / system；
 *  - resolved 是「实际生效」：system 时跟随 prefers-color-scheme；
 *  - 生效方式只有两个出口：
 *      1) 往 <html> 写 data-theme 属性 → 触发 styles/index.css 里的 CSS 变量切换；
 *      2) App.vue 读 isDark → 切 antd 的 darkAlgorithm + token。
 *    组件本身（写了 var(--xxx) 的那些）完全不需要感知主题。
 */
import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'

const STORAGE_KEY = 'ai_chat_theme'
const MEDIA_QUERY = '(prefers-color-scheme: dark)'

export type ThemeMode = 'light' | 'dark' | 'system'
export type ResolvedTheme = 'light' | 'dark'

/** 亮/暗两套主题色，与 index.css / App.vue 保持一致（用于 index.html 的 meta） */
const THEME_COLOR: Record<ResolvedTheme, string> = {
  light: '#fafafa',
  dark: '#0c0c0e',
}

function isThemeMode(value: unknown): value is ThemeMode {
  return value === 'light' || value === 'dark' || value === 'system'
}

function readMode(): ThemeMode {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return isThemeMode(raw) ? raw : 'light'
  } catch {
    return 'light'
  }
}

function systemPrefersDark(): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia(MEDIA_QUERY).matches
    : false
}

function resolveTheme(mode: ThemeMode): ResolvedTheme {
  if (mode === 'system') return systemPrefersDark() ? 'dark' : 'light'
  return mode
}

/** 把主题落到 DOM 上（data-theme / color-scheme / theme-color meta） */
export function applyTheme(resolved: ResolvedTheme): void {
  const root = document.documentElement
  root.dataset.theme = resolved
  // 让原生控件（滚动条、表单、下拉）也进入对应配色
  root.style.colorScheme = resolved
  const meta = document.querySelector('meta[name="theme-color"]')
  if (meta) meta.setAttribute('content', THEME_COLOR[resolved])
}

/**
 * 在 main.ts 里、挂载之前调用，避免「先亮后暗」的闪烁。
 * index.html 里还有一段等价的内联脚本，负责更早的时刻。
 */
export function applyThemeEarly(): void {
  applyTheme(resolveTheme(readMode()))
}

export const useThemeStore = defineStore('theme', () => {
  const mode = ref<ThemeMode>(readMode())
  const systemDark = ref(systemPrefersDark())

  const resolved = computed<ResolvedTheme>(() =>
    mode.value === 'system' ? (systemDark.value ? 'dark' : 'light') : mode.value,
  )
  const isDark = computed(() => resolved.value === 'dark')

  // 跟随系统时，监听系统配色变化
  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    const query = window.matchMedia(MEDIA_QUERY)
    query.addEventListener?.('change', (event) => {
      systemDark.value = event.matches
    })
  }

  watch(resolved, applyTheme, { immediate: true })
  watch(mode, (value) => {
    try {
      localStorage.setItem(STORAGE_KEY, value)
    } catch {
      /* 隐私模式下写入失败无所谓 */
    }
  })

  function setMode(value: ThemeMode): void {
    mode.value = value
  }

  /** 供工具栏上的小按钮使用：亮 ⇄ 暗（system 时按当前实际结果取反） */
  function toggle(): void {
    mode.value = resolved.value === 'dark' ? 'light' : 'dark'
  }

  return { mode, resolved, isDark, setMode, toggle }
})
