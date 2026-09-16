<template>
  <div class="code-block">
    <div class="code-block__header">
      <span class="code-block__lang">{{ lang || 'text' }}</span>
      <button type="button" class="code-block__copy" @click="handleCopy">
        {{ copied ? '已复制' : '复制' }}
      </button>
    </div>
    <pre><code v-html="highlighted"></code></pre>
  </div>
</template>

<script setup lang="ts">
/** 单个代码块组件：高亮 + 一键复制（用于分块预览 / 引用内容展示） */
import { computed, ref } from 'vue'
import { message } from 'ant-design-vue'

import { copyToClipboard } from '@/utils/format'
import { hljs } from '@/utils/markdown'

const props = withDefaults(defineProps<{ code: string; lang?: string }>(), { lang: 'text' })

const copied = ref(false)

const highlighted = computed(() => {
  const code = props.code || ''
  try {
    if (props.lang && hljs.getLanguage(props.lang)) {
      return hljs.highlight(code, { language: props.lang, ignoreIllegals: true }).value
    }
    return hljs.highlightAuto(code).value
  } catch {
    return code.replace(/[<>&]/g, (char) => ({ '<': '&lt;', '>': '&gt;', '&': '&amp;' })[char] as string)
  }
})

async function handleCopy() {
  try {
    await copyToClipboard(props.code)
    copied.value = true
    setTimeout(() => (copied.value = false), 1500)
  } catch {
    message.error('复制失败')
  }
}
</script>
