<template>
  <div class="chat-input">
    <div class="chat-input__wrapper" :class="{ 'is-focused': focused }">
      <a-textarea
        ref="textareaRef"
        v-model:value="text"
        class="chat-input__textarea"
        :placeholder="placeholder"
        :auto-size="{ minRows: 1, maxRows: 8 }"
        :maxlength="8000"
        :disabled="disabled"
        @focus="focused = true"
        @blur="focused = false"
        @press-enter="handleEnter"
      />

      <div class="chat-input__toolbar">
        <div class="chat-input__tools">
          <a-tooltip title="上传文档到知识库">
            <button type="button" class="tool-btn" @click="emit('upload')">
              <PaperClipOutlined />
            </button>
          </a-tooltip>
          <a-tooltip :title="autoRag ? 'RAG 检索已开启' : 'RAG 检索已关闭'">
            <button
              type="button"
              class="tool-btn"
              :class="{ active: autoRag }"
              @click="emit('update:autoRag', !autoRag)"
            >
              <DatabaseOutlined />
            </button>
          </a-tooltip>
          <SkillSelector
            :model-value="skillIds"
            @update:model-value="(value) => emit('update:skillIds', value)"
          />
          <McpSelector
            :model-value="mcpServerIds"
            @update:model-value="(value) => emit('update:mcpServerIds', value)"
          />
          <a-tooltip title="模型参数">
            <button type="button" class="tool-btn" @click="emit('params')">
              <SlidersOutlined />
            </button>
          </a-tooltip>

          <span class="chat-input__context">
            <a-tag v-if="knowledgeName" class="tag-mono chat-input__tag">
              <DatabaseOutlined /> {{ knowledgeName }}
            </a-tag>
            <a-tag v-if="modelName" class="chat-input__tag">{{ modelName }}</a-tag>
          </span>
        </div>

        <div class="chat-input__send">
          <a-tooltip v-if="generating" title="停止生成">
            <a-button shape="circle" danger @click="emit('stop')">
              <template #icon><BorderOutlined /></template>
            </a-button>
          </a-tooltip>
          <a-tooltip v-else title="发送（Enter）">
            <a-button type="primary" shape="circle" :disabled="!text.trim()" @click="submit">
              <template #icon><SendOutlined /></template>
            </a-button>
          </a-tooltip>
        </div>
      </div>
    </div>
    <p class="chat-input__hint">
      Enter 发送 · Shift + Enter 换行 · 内容由 AI 生成，请自行甄别
    </p>
  </div>
</template>

<script setup lang="ts">
/** 聊天输入框：自动高度 / Enter 发送 / 停止生成 / 快捷开关 */
import { nextTick, ref, watch } from 'vue'
import type { TextAreaProps } from 'ant-design-vue'
import {
  BorderOutlined,
  DatabaseOutlined,
  PaperClipOutlined,
  SendOutlined,
  SlidersOutlined,
} from '@ant-design/icons-vue'

import McpSelector from '@/components/mcp/McpSelector.vue'
import SkillSelector from '@/components/skill/SkillSelector.vue'

const props = withDefaults(
  defineProps<{
    modelValue?: string
    generating?: boolean
    disabled?: boolean
    autoRag?: boolean
    placeholder?: string
    modelName?: string | null
    knowledgeName?: string | null
    skillIds?: number[]
    mcpServerIds?: number[]
  }>(),
  {
    modelValue: '',
    generating: false,
    disabled: false,
    autoRag: true,
    placeholder: '输入你的问题…',
    modelName: null,
    knowledgeName: null,
    skillIds: () => [],
    mcpServerIds: () => [],
  },
)

const emit = defineEmits<{
  (event: 'update:modelValue', value: string): void
  (event: 'send', value: string): void
  (event: 'stop'): void
  (event: 'upload'): void
  (event: 'params'): void
  (event: 'update:autoRag', value: boolean): void
  (event: 'update:skillIds', value: number[]): void
  (event: 'update:mcpServerIds', value: number[]): void
}>()

const text = ref(props.modelValue)
const focused = ref(false)
const textareaRef = ref()

watch(
  () => props.modelValue,
  (value) => {
    if (value !== text.value) text.value = value
  },
)

watch(text, (value) => emit('update:modelValue', value))

function submit() {
  const value = text.value.trim()
  if (!value || props.generating) return
  emit('send', value)
  text.value = ''
  nextTick(() => textareaRef.value?.focus?.())
}

const handleEnter: TextAreaProps['onPressEnter'] = (event: KeyboardEvent) => {
  if (event.shiftKey) return
  event.preventDefault()
  submit()
}

defineExpose({ focus: () => textareaRef.value?.focus?.() })
</script>

<style scoped>
.chat-input {
  width: 100%;
}

.chat-input__wrapper {
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  background: var(--bg-card);
  padding: 10px 12px 8px;
  transition: border-color var(--transition), box-shadow var(--transition);
}

.chat-input__wrapper.is-focused {
  border-color: var(--brand);
  box-shadow: 0 0 0 3px rgba(22, 119, 255, 0.1);
}

.chat-input__textarea {
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
  resize: none;
  font-size: 14px;
  background: transparent;
}

.chat-input__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 6px;
}

.chat-input__tools {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.tool-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 15px;
  transition: var(--transition);
}

.tool-btn:hover,
.tool-btn.active {
  background: var(--brand-soft);
  color: var(--brand);
}

.chat-input__context {
  display: flex;
  align-items: center;
  gap: 4px;
  overflow: hidden;
}

.chat-input__tag {
  max-width: 170px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-inline-end: 0;
}

.chat-input__hint {
  margin: 8px 0 0;
  text-align: center;
  font-size: 12px;
  color: var(--text-tertiary);
}

@media (max-width: 768px) {
  .chat-input__hint {
    display: none;
  }
  .chat-input__context {
    display: none;
  }
}
</style>
