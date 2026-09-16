<template>
  <div class="markdown-body" ref="container" v-html="html"></div>
</template>

<script setup lang="ts">
/**
 * Markdown 渲染组件
 * - marked 解析 + highlight.js 代码高亮 + DOMPurify 清洗（防 XSS）
 * - 代码块自动注入「复制」按钮（事件委托，避免内联脚本被 DOMPurify 清理）
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'

import { copyToClipboard } from '@/utils/format'
import { renderMarkdown } from '@/utils/markdown'

const props = defineProps<{ content?: string | null }>()

const container = ref<HTMLElement | null>(null)
const html = computed(() => renderMarkdown(props.content))

async function attachCopyButtons() {
  await nextTick()
  const root = container.value
  if (!root) return
  root.querySelectorAll<HTMLElement>('.code-block').forEach((block) => {
    if (block.dataset.bound === '1') return
    block.dataset.bound = '1'
    block.addEventListener('click', async (event) => {
      const target = event.target as HTMLElement
      if (!target.classList.contains('code-block__copy')) return
      const code = block.querySelector('code')?.textContent ?? ''
      try {
        await copyToClipboard(code)
        target.textContent = '已复制'
        setTimeout(() => (target.textContent = '复制'), 1500)
      } catch {
        message.error('复制失败，请手动选择复制')
      }
    })
  })
}

onMounted(attachCopyButtons)
watch(html, attachCopyButtons)
onBeforeUnmount(() => {
  container.value?.querySelectorAll('.code-block').forEach((block) => {
    block.replaceWith(block.cloneNode(true))
  })
})

defineExpose({ refresh: attachCopyButtons })
</script>

<style scoped>
.markdown-body {
  white-space: normal;
}
</style>
