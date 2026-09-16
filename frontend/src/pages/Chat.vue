<template>
  <ChatLayout>
    <ChatHeader
      :title="chatStore.currentConversation?.title || '新对话'"
      @toggle-sidebar="emitToggleSidebar"
      @open-params="paramsOpen = true"
      @action="handleHeaderAction"
    />

    <div class="chat-page">
      <!-- 消息区 -->
      <div ref="scrollRef" class="chat-page__messages" @scroll="handleScroll">
        <div class="chat-page__messages-inner">
          <!-- 空状态：欢迎 + 推荐问题 -->
          <div v-if="!chatStore.hasMessages" class="chat-page__welcome">
            <EmptyState
              :icon="CommentOutlined"
              title="开始一段新的对话"
              description="选择模型（可再选一个知识库），然后输入你的问题。"
            >
              <div class="chat-page__suggestions">
                <button
                  v-for="item in suggestions"
                  :key="item"
                  type="button"
                  class="chat-page__suggestion"
                  @click="handleSend(item)"
                >
                  {{ item }}
                </button>
              </div>
            </EmptyState>
          </div>

          <template v-else>
            <ChatMessage
              v-for="item in chatStore.messages"
              :key="item.id"
              :message="item"
              :user-initial="userStore.avatarText"
              :show-usage="settings.showTokenUsage"
              @regenerate="handleRegenerate"
              @edit="handleEdit"
            />
          </template>

          <!-- 提示 / 通知 -->
          <div v-if="chatStore.notices.length" class="chat-page__notices">
            <a-alert
              v-for="(notice, index) in chatStore.notices"
              :key="index"
              :message="notice"
              type="info"
              show-icon
              banner
              closable
              @close="chatStore.notices.splice(index, 1)"
            />
          </div>
        </div>
      </div>

      <!-- 输入区 -->
      <div class="chat-page__input">
        <div class="chat-page__input-inner">
          <ChatInput
            ref="inputRef"
            v-model="draft"
            :generating="chatStore.streaming"
            :auto-rag="settings.autoRag"
            :model-name="currentModelName"
            :knowledge-name="currentKnowledgeName"
            @send="handleSend"
            @stop="chatStore.stopGenerate"
            :skill-ids="settings.skillIds"
            :mcp-server-ids="settings.mcpServerIds"
            @upload="goToKnowledge"
            @params="paramsOpen = true"
            @update:auto-rag="(value) => (settings.autoRag = value)"
            @update:skill-ids="(value) => (settings.skillIds = value)"
            @update:mcp-server-ids="(value) => (settings.mcpServerIds = value)"
          />
        </div>
      </div>
    </div>

    <ModelParamsPanel v-model:open="paramsOpen" />
  </ChatLayout>
</template>

<script setup lang="ts">
/** AI 聊天页：消息流 + 流式生成 + 会话操作 */
import { computed, h, nextTick, onMounted, ref, watch } from 'vue'
import { Modal, message as antMessage } from 'ant-design-vue'
import { useRouter } from 'vue-router'

import ChatHeader from '@/components/chat/ChatHeader.vue'
import ChatInput from '@/components/chat/ChatInput.vue'
import ChatMessage from '@/components/chat/ChatMessage.vue'
import ModelParamsPanel from '@/components/chat/ModelParamsPanel.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import ChatLayout from '@/layouts/ChatLayout.vue'
import { useChatStore } from '@/stores/chat'
import { useKnowledgeStore } from '@/stores/knowledge'
import { useModelStore } from '@/stores/model'
import { useSettingsStore } from '@/stores/settings'
import { useUserStore } from '@/stores/user'
import type { ChatMessage as ChatMessageType } from '@/types'
import { CommentOutlined } from '@ant-design/icons-vue'

const router = useRouter()
const chatStore = useChatStore()
const modelStore = useModelStore()
const knowledgeStore = useKnowledgeStore()
const settings = useSettingsStore()
const userStore = useUserStore()

const draft = ref('')
const paramsOpen = ref(false)
const scrollRef = ref<HTMLElement | null>(null)
const inputRef = ref<InstanceType<typeof ChatInput> | null>(null)
let autoScroll = true

const suggestions = [
  '用 Python 写一个 FastAPI 的 Hello World 示例',
  '解释一下 RAG 的检索流程和常见优化手段',
  '帮我把这段需求拆解成技术方案与任务清单',
  'Vue3 中 ref 和 reactive 的区别是什么？',
]

const currentModelName = computed(() => {
  const model = modelStore.models.find((item) => item.id === settings.modelId)
  return model?.name || modelStore.defaultModel?.name || null
})

const currentKnowledgeName = computed(() => {
  const kb = knowledgeStore.knowledgeBases.find((item) => item.id === settings.knowledgeBaseId)
  return kb?.name || null
})

/** 移动端：顶部菜单按钮打开会话列表抽屉（桌面端：折叠 / 展开固定侧边栏） */
const emitToggleSidebar = () => {
  if (window.innerWidth <= 992) {
    settings.mobileSidebarOpen = true
  } else {
    settings.sidebarCollapsed = !settings.sidebarCollapsed
  }
}

onMounted(() => {
  modelStore.fetchModels().catch(() => undefined)
  knowledgeStore.fetchKnowledgeBases().catch(() => undefined)
  if (!settings.modelId && modelStore.defaultModel) {
    settings.modelId = modelStore.defaultModel.id
  }
})

// 新消息自动滚到底部
watch(
  () => chatStore.messages.map((item) => item.content.length).join(','),
  async () => {
    if (!autoScroll) return
    await nextTick()
    scrollToBottom()
  },
)

watch(
  () => chatStore.messages.length,
  async () => {
    await nextTick()
    scrollToBottom()
  },
)

function scrollToBottom() {
  const el = scrollRef.value
  if (!el) return
  el.scrollTop = el.scrollHeight
}

function handleScroll() {
  const el = scrollRef.value
  if (!el) return
  autoScroll = el.scrollHeight - el.scrollTop - el.clientHeight < 120
}

async function handleSend(content: string) {
  autoScroll = true
  await chatStore.sendMessage(content)
}

function handleRegenerate(target: ChatMessageType) {
  // 重新生成最后一条用户提问
  const index = chatStore.messages.findIndex((item) => item.id === target.id)
  const lastUser = [...chatStore.messages.slice(0, index)].reverse().find((item) => item.role === 'user')
  if (!lastUser) {
    antMessage.warning('没有找到可重新生成的问题')
    return
  }
  chatStore.resend(lastUser.content).catch(() => antMessage.error('重新生成失败'))
}

function handleEdit(payload: { message: ChatMessageType; content: string }) {
  chatStore.editAndResend(payload.message, payload.content).catch(() => antMessage.error('重新发送失败'))
}

async function handleHeaderAction(key: string) {
  if (key === 'clear') {
    Modal.confirm({
      title: '清空当前对话',
      content: '将删除该会话下的所有消息（会话本身保留），确定继续吗？',
      okText: '清空',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        await chatStore.clearCurrentConversation()
        antMessage.success('已清空当前对话')
      },
    })
  } else if (key === 'rename') {
    const title = chatStore.currentConversation?.title || ''
    let value = title
    Modal.confirm({
      title: '重命名会话',
      content: () =>
        h('input', {
          class: 'ant-input',
          value,
          onInput: (event: Event) => (value = (event.target as HTMLInputElement).value),
        }),
      okText: '保存',
      cancelText: '取消',
      onOk: async () => {
        if (!chatStore.currentId || !value.trim()) return
        await chatStore.renameConversation(chatStore.currentId, value.trim())
      },
    })
  } else if (key === 'knowledge') {
    await router.push('/admin/knowledge')
  } else if (key === 'home') {
    await router.push('/')
  } else if (key === 'admin') {
    await router.push('/admin/dashboard')
  }
}

async function goToKnowledge() {
  await router.push('/admin/knowledge')
}

function focusInput() {
  inputRef.value?.focus()
}

defineExpose({ focusInput })
</script>


<style scoped>
.chat-page {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--bg-card);
}

.chat-page__messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 20px 0 8px;
}

.chat-page__messages-inner {
  max-width: 880px;
  margin: 0 auto;
  padding: 0 20px;
}

.chat-page__welcome {
  padding-top: 6vh;
}

.chat-page__suggestions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  max-width: 560px;
  margin-top: 4px;
}

.chat-page__suggestion {
  padding: 8px 14px;
  font-size: 13px;
  color: var(--text-primary);
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 999px;
  cursor: pointer;
  transition: var(--transition);
}

.chat-page__suggestion:hover {
  border-color: var(--brand);
  color: var(--brand);
  background: var(--brand-soft);
}

.chat-page__notices {
  margin: 8px 0 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.chat-page__input {
  border-top: 1px solid var(--border-color);
  background: var(--bg-card);
  padding: 14px 0 10px;
}

.chat-page__input-inner {
  max-width: 880px;
  margin: 0 auto;
  padding: 0 20px;
}
</style>
