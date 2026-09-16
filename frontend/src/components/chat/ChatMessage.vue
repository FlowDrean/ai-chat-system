<template>
  <div class="chat-message" :class="[`is-${message.role}`, { 'is-error': isFailed }]">
    <div class="chat-message__avatar" :class="`is-${message.role}`">
      <template v-if="message.role === 'user'">
        <span>{{ userInitial }}</span>
      </template>
      <template v-else>
        <svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true">
          <path
            d="M12 2.6l1.9 4.9 4.9 1.9-4.9 1.9L12 16.2l-1.9-4.9-4.9-1.9 4.9-1.9L12 2.6z"
            fill="currentColor"
          />
        </svg>
      </template>
    </div>

    <div class="chat-message__body">
      <div class="chat-message__head">
        <span class="chat-message__name">{{ message.role === 'user' ? '我' : 'AI 助手' }}</span>
        <a-tag v-if="message.model_name && message.role === 'assistant'" class="chat-message__model">
          {{ message.model_name }}
        </a-tag>
        <span v-if="message.role === 'assistant' && isRag" class="chat-message__badge">
          <DatabaseOutlined /> 知识库
        </span>
        <span class="chat-message__time">{{ formatDateTime(message.created_at, 'MM-DD HH:mm') }}</span>
      </div>

      <!-- 用户消息：纯文本 + 编辑 -->
      <div v-if="message.role === 'user'" class="chat-message__bubble is-user">
        <template v-if="editing">
          <a-textarea v-model:value="draft" :rows="3" :maxlength="8000" />
          <div class="chat-message__edit-actions">
            <a-button size="small" @click="cancelEdit">取消</a-button>
            <a-button size="small" type="primary" @click="submitEdit">重新发送</a-button>
          </div>
        </template>
        <template v-else>
          <div class="chat-message__text">{{ message.content }}</div>
          <div class="chat-message__actions is-user-actions">
            <button type="button" class="chat-action" title="复制" @click="copyContent">
              <CopyOutlined />
            </button>
            <button type="button" class="chat-action" title="编辑并重新发送" @click="startEdit">
              <EditOutlined />
            </button>
          </div>
        </template>
      </div>

      <!-- AI 消息 -->
      <template v-else>
        <a-alert
          v-if="isFailed"
          type="error"
          show-icon
          class="chat-message__alert"
          :message="message.error_message || '模型调用失败，请检查模型配置或 API Key。'"
        />
        <div v-if="message.status === 'stopped'" class="chat-message__stopped">
          <PauseCircleOutlined /> 已停止生成
        </div>

        <div v-if="message.streaming && !message.content" class="chat-message__thinking">
          <span class="dot" /><span class="dot" /><span class="dot" />
          <span>AI 正在思考…</span>
        </div>

        <div v-if="message.content" class="chat-message__content">
          <MarkdownRenderer :content="message.content" />
          <span v-if="message.streaming" class="chat-message__caret" />
        </div>

        <div v-if="!message.streaming && message.content" class="chat-message__actions">
          <button type="button" class="chat-action" title="复制回答" @click="copyContent">
            <CopyOutlined />
          </button>
          <button type="button" class="chat-action" title="重新生成" @click="emit('regenerate', message)">
            <ReloadOutlined />
          </button>
          <button
            type="button"
            class="chat-action"
            :class="{ active: feedback === 'like' }"
            title="回答有帮助"
            @click="setFeedback('like')"
          >
            <LikeOutlined />
          </button>
          <button
            type="button"
            class="chat-action"
            :class="{ active: feedback === 'dislike' }"
            title="回答需改进"
            @click="setFeedback('dislike')"
          >
            <DislikeOutlined />
          </button>
          <span v-if="showUsage" class="chat-message__usage">
            耗时 {{ formatDuration(message.latency_ms) }}
            <template v-if="message.total_tokens">
              · Token {{ formatNumber(message.total_tokens) }}
            </template>
          </span>
        </div>

        <SkillCallList v-if="message.skills?.length" :calls="message.skills" />

        <RagSource v-if="message.sources?.length" :sources="message.sources" />

        <div v-if="isFailed" class="chat-message__retry">
          <a-button size="small" type="primary" ghost @click="emit('regenerate', message)">
            <template #icon><ReloadOutlined /></template>
            重新生成
          </a-button>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * 聊天消息组件
 * UserMessage：右侧气泡 + 复制 / 编辑重发
 * AIMessage ：Markdown / 代码高亮 / 复制 / 重新生成 / 点赞点踩 / RAG 引用 / Token 统计
 */
import { computed, ref } from 'vue'
import { message as antMessage } from 'ant-design-vue'
import {
  CopyOutlined,
  DatabaseOutlined,
  DislikeOutlined,
  EditOutlined,
  LikeOutlined,
  PauseCircleOutlined,
  ReloadOutlined,
} from '@ant-design/icons-vue'

import type { ChatMessage } from '@/types'
import { copyToClipboard, formatDateTime, formatDuration, formatNumber } from '@/utils/format'
import SkillCallList from '@/components/skill/SkillCallList.vue'
import MarkdownRenderer from './MarkdownRenderer.vue'
import RagSource from './RagSource.vue'

const props = withDefaults(
  defineProps<{
    message: ChatMessage
    userInitial?: string
    showUsage?: boolean
  }>(),
  { userInitial: '我', showUsage: true },
)

const emit = defineEmits<{
  (event: 'regenerate', message: ChatMessage): void
  (event: 'edit', payload: { message: ChatMessage; content: string }): void
}>()

const editing = ref(false)
const draft = ref('')
const feedback = ref<'like' | 'dislike' | null>(null)

const isFailed = computed(() => props.message.status === 'error' || props.message.failed)
const isRag = computed(() => Boolean(props.message.sources?.length))

function startEdit() {
  draft.value = props.message.content
  editing.value = true
}

function cancelEdit() {
  editing.value = false
  draft.value = ''
}

function submitEdit() {
  const content = draft.value.trim()
  if (!content) {
    antMessage.warning('内容不能为空')
    return
  }
  editing.value = false
  emit('edit', { message: props.message, content })
}

async function copyContent() {
  try {
    await copyToClipboard(props.message.content)
    antMessage.success('已复制到剪贴板')
  } catch {
    antMessage.error('复制失败')
  }
}

function setFeedback(value: 'like' | 'dislike') {
  feedback.value = feedback.value === value ? null : value
  if (feedback.value) antMessage.success(feedback.value === 'like' ? '感谢反馈！' : '已记录，我们会持续优化')
}
</script>

<style scoped>
.chat-message {
  display: flex;
  gap: 12px;
  padding: 8px 0 20px;
  animation: fade-in var(--transition) both;
}

.chat-message.is-user {
  flex-direction: row-reverse;
}

.chat-message__avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 9px;
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
}

.chat-message__avatar.is-assistant {
  background: var(--brand);
  color: var(--brand-contrast);
}

.chat-message__avatar.is-user {
  background: var(--bg-card);
  color: var(--text-primary);
  border: 1px solid var(--border-strong);
}

.chat-message__body {
  min-width: 0;
  max-width: min(820px, 100%);
  flex: 1;
}

.chat-message.is-user .chat-message__body {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.chat-message__head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

.chat-message.is-user .chat-message__head {
  flex-direction: row-reverse;
}

.chat-message__name {
  font-weight: 600;
  color: var(--text-primary);
}

.chat-message__model {
  margin-inline-end: 0;
  font-size: 11px;
}

.chat-message__badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--brand);
}

.chat-message__bubble {
  padding: 10px 14px;
  border-radius: var(--radius);
  background: var(--brand);
  border: 1px solid var(--brand);
  color: var(--brand-contrast);
  white-space: pre-wrap;
  word-break: break-word;
  max-width: 100%;
}

/* 深色气泡内的操作按钮 / 编辑框适配 */
.chat-message__bubble .chat-action {
  color: var(--brand-contrast-soft);
}

.chat-message__bubble .chat-action:hover {
  background: var(--brand-contrast-faint);
  color: var(--brand-contrast);
}

.chat-message__bubble :deep(.ant-input),
.chat-message__bubble :deep(.ant-input:focus) {
  color: var(--text-primary);
  background: var(--bg-card);
}

.chat-message__text {
  font-size: 14px;
  line-height: 1.7;
}

.chat-message__edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}

.chat-message__content {
  font-size: 14px;
}

.chat-message__alert {
  margin-bottom: 8px;
}

.chat-message__stopped {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 6px;
  font-size: 12px;
  color: var(--text-secondary);
}

.chat-message__thinking {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-secondary);
}

.chat-message__thinking .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--brand);
  opacity: 0.4;
  animation: blink 1.2s infinite ease-in-out;
}

.chat-message__thinking .dot:nth-child(2) {
  animation-delay: 0.15s;
}
.chat-message__thinking .dot:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes blink {
  0%,
  80%,
  100% {
    opacity: 0.25;
    transform: translateY(0);
  }
  40% {
    opacity: 1;
    transform: translateY(-2px);
  }
}

.chat-message__caret {
  display: inline-block;
  width: 6px;
  height: 15px;
  margin-left: 2px;
  background: var(--brand);
  vertical-align: text-bottom;
  animation: blink-caret 1s step-end infinite;
}

@keyframes blink-caret {
  50% {
    opacity: 0;
  }
}

.chat-message__actions {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 8px;
  opacity: 0.75;
  transition: opacity var(--transition);
}

.chat-message__actions:hover {
  opacity: 1;
}

.chat-message__actions.is-user-actions {
  justify-content: flex-end;
  margin-top: 6px;
}

.chat-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: var(--transition);
}

.chat-action:hover,
.chat-action.active {
  background: var(--bg-hover);
  color: var(--brand);
}

.chat-message__usage {
  margin-left: 6px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.chat-message__retry {
  margin-top: 10px;
}
</style>
