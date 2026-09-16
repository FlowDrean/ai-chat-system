<template>
  <a-config-provider :locale="zhCN" :theme="themeConfig">
    <router-view />
  </a-config-provider>
</template>

<script setup lang="ts">
/**
 * 根组件：Ant Design Vue 全局配置（中文语言包 + 黑白灰主题 + 亮/暗两套 token）
 *
 * 主题策略：
 *  - 只认黑白灰：强调色 = 近黑（亮色）/ 近白（暗色），交互态用一档浅（深）灰；
 *  - 暗色下 --brand 反转成近白，主按钮 / 选中项 / Logo 自动变成「白底黑字」，
 *    与亮色的「黑底白字」对称；
 *  - 语义色（成功 / 警告 / 失败）保持低饱和，只用于状态提示；
 *  - 表格 / 卡片 / 菜单全部走「发丝线 + 浅（深）灰底」，不使用彩色描边。
 */
import { theme as antdTheme } from 'ant-design-vue'
import zhCN from 'ant-design-vue/es/locale/zh_CN'
import dayjs from 'dayjs'
import 'dayjs/locale/zh-cn'
import { computed } from 'vue'

import { useThemeStore } from '@/stores/theme'

dayjs.locale('zh-cn')

const themeStore = useThemeStore()
const isDark = computed(() => themeStore.isDark)

/** 不随明暗变化的 token */
const sharedToken = {
  borderRadius: 8,
  borderRadiusLG: 10,
  borderRadiusSM: 6,
  fontSize: 14,
  controlHeight: 34,
  lineWidth: 1,
  wireframe: false,
  controlOutlineWidth: 2,
  fontFamily:
    '-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif',
}

const lightToken = {
  colorPrimary: '#111114',
  colorPrimaryHover: '#2b2b31',
  colorPrimaryActive: '#000000',
  colorLink: '#111114',
  colorLinkHover: '#2b2b31',
  colorInfo: '#111114',
  colorSuccess: '#2f7d5b',
  colorWarning: '#8a6a1f',
  colorError: '#b3261e',

  colorText: '#16161a',
  colorTextSecondary: '#6b7280',
  colorTextTertiary: '#8b8b94',
  colorTextQuaternary: '#949499',
  colorIcon: '#6b7280',
  colorIconHover: '#16161a',
  colorBorder: '#e6e6e9',
  colorBorderSecondary: '#efeff1',
  colorSplit: '#efeff1',
  colorBgBase: '#ffffff',
  colorBgLayout: '#fafafa',
  colorBgContainer: '#ffffff',
  colorBgElevated: '#ffffff',

  /* 焦点环统一为近黑半透明，避免任何默认蓝色光晕 */
  controlOutline: 'rgba(17, 17, 20, 0.08)',

  boxShadow: '0 1px 2px rgba(16, 16, 20, 0.04)',
  boxShadowSecondary: '0 1px 2px rgba(16, 16, 20, 0.04), 0 10px 30px rgba(16, 16, 20, 0.07)',
}

const darkToken = {
  colorPrimary: '#f4f4f5',
  colorPrimaryHover: '#ffffff',
  colorPrimaryActive: '#e4e4e7',
  colorLink: '#f4f4f5',
  colorLinkHover: '#ffffff',
  colorInfo: '#f4f4f5',
  colorSuccess: '#57b98a',
  colorWarning: '#d0a844',
  colorError: '#ef6f62',

  colorText: '#f2f2f4',
  colorTextSecondary: '#a1a1aa',
  colorTextTertiary: '#71717a',
  colorTextQuaternary: '#71717a',
  colorIcon: '#a1a1aa',
  colorIconHover: '#f2f2f4',
  colorBorder: '#26262a',
  colorBorderSecondary: '#1f1f23',
  colorSplit: '#1f1f23',
  colorBgBase: '#0c0c0e',
  colorBgLayout: '#0c0c0e',
  colorBgContainer: '#141416',
  colorBgElevated: '#1a1a1d',

  controlOutline: 'rgba(244, 244, 245, 0.14)',

  boxShadow: '0 1px 2px rgba(0, 0, 0, 0.5)',
  boxShadowSecondary: '0 1px 2px rgba(0, 0, 0, 0.5), 0 12px 32px rgba(0, 0, 0, 0.55)',
}

/**
 * 组件级 token。
 *
 * 重要：ant-design-vue 4.2.6 的组件 token 仍是 **v4 命名**，例如
 *   Menu  -> colorItemBgSelected / colorItemBgHover
 *   （Table 的表头 / 行悬停底色会被内部重新覆盖，改用 styles/index.css 收口）
 * antd v5 的 itemSelectedBg、headerBg、itemSelectedColor 等名字在本版本里不会生效。
 * 其余组件（Segmented / Slider / Progress / Tabs / Switch / Tag / Card ）默认就走全局 token
 * 或 styles/index.css 里的收口样式（如 Segmented 选中态），无需逐个覆盖。
 */
const lightComponents = {
  /* 侧栏导航选中项：反白药丸（黑底白字），与主按钮 / Logo 一致 */
  Menu: {
    colorItemBgSelected: '#111114',
    colorItemTextSelected: '#ffffff',
    colorItemBgHover: '#f4f4f5',
    colorItemBgActive: '#f4f4f5',
    radiusItem: 8,
    colorActiveBarWidth: 0,
    colorActiveBarBorderSize: 0,
  },
}

const darkComponents = {
  /* 暗色下反过来：白底黑字的药丸 */
  Menu: {
    colorItemBgSelected: '#f4f4f5',
    colorItemTextSelected: '#111114',
    colorItemBgHover: '#1e1e22',
    colorItemBgActive: '#1e1e22',
    radiusItem: 8,
    colorActiveBarWidth: 0,
    colorActiveBarBorderSize: 0,
  },

  /**
   * 暗色下主色是近白，这些「实心高亮」组件的底色会变成浅色，
   * 而 antd 默认把前景画成白色（colorTextLightSolid） 白底白字 / 白底白勾。
   * 按组件逐个翻转，不会影响 Tooltip / Badge 这类真正深底的地方。
   */
  Button: { colorTextLightSolid: '#111114' },
  Switch: { colorTextLightSolid: '#111114' },
  Steps: { colorTextLightSolid: '#111114' },
  FloatButton: { colorTextLightSolid: '#111114' },
}

const themeConfig = computed(() => ({
  algorithm: isDark.value ? antdTheme.darkAlgorithm : undefined,
  token: {
    ...sharedToken,
    ...(isDark.value ? darkToken : lightToken),
  },
  components: isDark.value ? darkComponents : lightComponents,
}))
</script>
