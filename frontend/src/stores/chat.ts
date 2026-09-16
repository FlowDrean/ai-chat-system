/**
 * 聊天状态：会话列表 / 消息流 / SSE 流式生成 / 重新生成 / 停止生成
 *
 * 关键点：
 * 1. 用户消息乐观插入（临时 id 为负数），收到 meta 事件后用服务端消息替换；
 * 2. 助手消息先插入占位对象，token 直接追加到该响应式对象上，
 *    因此流式过程中无需重建数组，性能与体验都更好；
 * 3. 停止生成 = AbortController.abort()，后端在生成器 finally 中把已生成内容
 *    以 stopped 状态落库，不会丢消息。
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { message as antMessage } from 'ant-design-vue'

import { chatApi } from '@/api/chat'
import { streamChat } from '@/utils/sse'
import type { ChatMessage, ChatRequestPayload, Conversation, RagSource, SkillCall, UsageInfo } from '@/types'
import { useSettingsStore } from './settings'

const TEMP_USER_ID = -1
const TEMP_ASSISTANT_ID = -2

export const useChatStore = defineStore('chat', () => {
  const settings = useSettingsStore()

  const conversations = ref<Conversation[]>([])
  const currentId = ref<number | null>(null)
  const messages = ref<ChatMessage[]>([])
  const loadingConversations = ref(false)
  const loadingMessages = ref(false)
  const streaming = ref(false)
  const thinking = ref(false)
  const errorMessage = ref<string | null>(null)
  const notices = ref<string[]>([])
  const lastUsage = ref<UsageInfo | null>(null)
  const currentRoute = ref<'rag' | 'direct' | null>(null)

  let controller: AbortController | null = null

  const currentConversation = computed(
    () => conversations.value.find((item) => item.id === currentId.value) || null,
  )
  const hasMessages = computed(() => messages.value.length > 0)
  const favoriteConversations = computed(() => conversations.value.filter((item) => item.is_favorite))

  /* ------------------------------------------------------------------ 会话 */
  async function fetchConversations(keyword?: string) {
    loadingConversations.value = true
    try {
      const data = await chatApi.listConversations({ keyword, page_size: 100 })
      conversations.value = data.items
      return data.items
    } finally {
      loadingConversations.value = false
    }
  }

  async function createConversation(payload: Partial<Conversation> = {}) {
    const conversation = await chatApi.createConversation({
      model_id: payload.model_id ?? settings.modelId,
      knowledge_base_id: payload.knowledge_base_id ?? settings.knowledgeBaseId,
      prompt_id: payload.prompt_id ?? settings.promptId,
      ...payload,
    })
    conversations.value.unshift(conversation)
    currentId.value = conversation.id
    messages.value = []
    return conversation
  }

  async function selectConversation(id: number) {
    currentId.value = id
    await loadMessages(id)
  }

  async function loadMessages(id: number) {
    loadingMessages.value = true
    try {
      const data = await chatApi.listMessages(id, { limit: 200 })
      messages.value = data.map((item) => ({ ...item, streaming: false }))
      const conversation = conversations.value.find((item) => item.id === id)
      if (conversation) {
        settings.modelId = conversation.model_id ?? settings.modelId
        settings.knowledgeBaseId = conversation.knowledge_base_id ?? null
        settings.promptId = conversation.prompt_id ?? null
        settings.skillIds = conversation.skill_ids || []
        settings.mcpServerIds = conversation.mcp_server_ids || []
        if (conversation.params) {
          settings.params = { ...settings.params, ...(conversation.params as object) }
        }
      }
      return messages.value
    } finally {
      loadingMessages.value = false
    }
  }

  async function renameConversation(id: number, title: string) {
    const updated = await chatApi.updateConversation(id, { title })
    patchConversation(updated)
    return updated
  }

  async function toggleFavorite(conversation: Conversation) {
    const updated = await chatApi.updateConversation(conversation.id, {
      is_favorite: !conversation.is_favorite,
    })
    patchConversation(updated)
    return updated
  }

  async function archiveConversation(conversation: Conversation) {
    const updated = await chatApi.updateConversation(conversation.id, {
      is_archived: !conversation.is_archived,
    })
    patchConversation(updated)
    return updated
  }

  async function deleteConversation(id: number) {
    await chatApi.deleteConversation(id)
    conversations.value = conversations.value.filter((item) => item.id !== id)
    if (currentId.value === id) {
      currentId.value = null
      messages.value = []
    }
  }

  async function clearCurrentConversation() {
    if (!currentId.value) return
    const updated = await chatApi.clearConversation(currentId.value)
    patchConversation(updated)
    messages.value = []
    return updated
  }

  function patchConversation(conversation: Conversation) {
    const index = conversations.value.findIndex((item) => item.id === conversation.id)
    if (index >= 0) conversations.value[index] = { ...conversations.value[index], ...conversation }
    else conversations.value.unshift(conversation)
  }

  /* ------------------------------------------------------------------ 消息 */
  function pushNotice(text: string) {
    notices.value.push(text)
    if (notices.value.length > 5) notices.value.shift()
  }

  async function sendMessage(content: string, options: { regenerate?: boolean } = {}) {
    const text = content.trim()
    if (!text) return
    if (streaming.value) {
      antMessage.warning('正在生成回复，请稍候或先停止生成')
      return
    }

    // 1. 没有会话则先创建
    if (!currentId.value) {
      try {
        await createConversation()
      } catch {
        return
      }
    }
    if (!currentId.value) return

    errorMessage.value = null
    notices.value = []
    lastUsage.value = null

    const conversationId = currentId.value

    // 2. 乐观插入用户消息
    let userMessageIndex = -1
    if (!options.regenerate) {
      messages.value.push({
        id: TEMP_USER_ID,
        conversation_id: conversationId,
        role: 'user',
        content: text,
        status: 'done',
        prompt_tokens: 0,
        completion_tokens: 0,
        total_tokens: 0,
        latency_ms: 0,
      })
      userMessageIndex = messages.value.length - 1
    }

    // 3. 助手占位消息
    messages.value.push({
      id: TEMP_ASSISTANT_ID,
      conversation_id: conversationId,
      role: 'assistant',
      content: '',
      status: 'streaming',
      streaming: true,
      model_name: null,
      sources: [],
      skills: [],
      prompt_tokens: 0,
      completion_tokens: 0,
      total_tokens: 0,
      latency_ms: 0,
    })
    const assistant = messages.value[messages.value.length - 1]
    const userRef = userMessageIndex >= 0 ? messages.value[userMessageIndex] : null

    const payload: ChatRequestPayload = {
      content: text,
      conversation_id: conversationId,
      model_id: settings.modelId,
      knowledge_base_id: settings.knowledgeBaseId ?? 0,
      prompt_id: settings.promptId,
      skill_ids: settings.skillIds,
      mcp_server_ids: settings.mcpServerIds,
      params: options.regenerate ? undefined : settings.params,
      stream: true,
      regenerate: options.regenerate ?? false,
      use_rag: settings.knowledgeBaseId ? settings.autoRag : false,
    }

    streaming.value = true
    thinking.value = true
    controller = new AbortController()

    try {
      await streamChat(
        payload,
        {
          onMeta(event) {
            thinking.value = false
            // 会话信息
            const conversation = event.conversation as Conversation | undefined
            if (conversation) {
              patchConversation(conversation)
              currentId.value = conversation.id
            }
            // 用服务端消息替换临时用户消息
            const serverUser = event.user_message as ChatMessage | null
            if (serverUser && userRef) {
              Object.assign(userRef, serverUser)
              userRef.status = 'done'
            }
            // 助手消息 id / 模型信息
            const serverAssistant = event.assistant_message as ChatMessage | null
            if (serverAssistant) {
              assistant.id = serverAssistant.id
              assistant.model_name = serverAssistant.model_name
              assistant.provider = serverAssistant.provider
              assistant.model_id = serverAssistant.model_id
              assistant.knowledge_base_id = serverAssistant.knowledge_base_id
            }
            const model = event.model as { name?: string; model_name?: string } | undefined
            if (!assistant.model_name && model?.model_name) assistant.model_name = model.model_name
          },
          onRoute(event) {
            currentRoute.value = event.use_rag ? 'rag' : 'direct'
          },
          onSources(event) {
            assistant.sources = (event.sources as RagSource[]) || []
          },
          onToken(token) {
            thinking.value = false
            assistant.content += token
          },
          onSkill(event) {
            const phase = String(event.phase || '')
            const list = (assistant.skills ||= [] as SkillCall[])
            if (phase === 'call') {
              list.push({
                name: String(event.name || event.tool_name || '技能'),
                tool_name: (event.tool_name as string) || null,
                type: (event.skill_type as string) || null,
                source: (event.source as string) || 'skill',
                server: (event.server as string) || null,
                status: 'running',
                arguments: (event.arguments as Record<string, unknown>) || null,
              })
              thinking.value = false
              currentRoute.value = currentRoute.value || 'direct'
            } else if (phase === 'result') {
              const index = [...list]
                .map((item, i) => ({ item, i }))
                .reverse()
                .find(
                  ({ item }) =>
                    item.status === 'running' &&
                    (!event.tool_name || item.tool_name === event.tool_name),
                )?.i
              const record: SkillCall = {
                name: String(event.name || event.tool_name || '技能'),
                tool_name: (event.tool_name as string) || null,
                type: (event.skill_type as string) || null,
                source: (event.source as string) || 'skill',
                server: (event.server as string) || null,
                status: String(event.status || 'ok'),
                arguments: (event.arguments as Record<string, unknown>) || null,
                output: (event.output as string) || '',
                latency_ms: Number(event.latency_ms || 0),
              }
              if (index !== undefined) list[index] = record
              else list.push(record)
            }
          },
          onNotice(event) {
            if (event.message) pushNotice(String(event.message))
          },
          onError(event) {
            assistant.status = 'error'
            assistant.error_message = String(event.message || '模型调用失败')
            if (event.partial) assistant.content += String(event.partial)
            errorMessage.value = assistant.error_message
          },
          onDone(event) {
            const serverMessage = event.message as ChatMessage | undefined
            if (serverMessage) {
              Object.assign(assistant, serverMessage, { streaming: false })
            } else {
              assistant.streaming = false
            }
            if (Array.isArray(event.skills)) {
              assistant.skills = event.skills as SkillCall[]
            }
            const usage = event.usage as UsageInfo | undefined
            if (usage) lastUsage.value = usage
            const conversation = event.conversation as Conversation | undefined
            if (conversation) patchConversation(conversation)
          },
        },
        controller.signal,
      )
    } catch (error) {
      const aborted = (error as Error)?.name === 'AbortError'
      assistant.streaming = false
      if (aborted) {
        assistant.status = 'stopped'
        if (!assistant.content) assistant.content = '（已停止生成）'
      } else {
        assistant.status = 'error'
        assistant.failed = true
        assistant.error_message = (error as Error)?.message || '网络连接失败'
        errorMessage.value = assistant.error_message
      }
    } finally {
      streaming.value = false
      thinking.value = false
      controller = null
      assistant.streaming = false
      // 同步会话计数与排序
      fetchConversations().catch(() => undefined)
    }
  }

  function stopGenerate() {
    if (controller) {
      controller.abort()
      controller = null
    }
    streaming.value = false
    thinking.value = false
  }

  async function regenerate() {
    const lastUser = [...messages.value].reverse().find((item) => item.role === 'user')
    if (!lastUser) return
    await resend(lastUser.content)
  }

  /** 删除最后一条助手回答后重新提问（用于「重新生成」） */
  async function resend(content: string) {
    if (streaming.value) return
    const lastAssistant = [...messages.value].reverse().find((item) => item.role === 'assistant')
    if (lastAssistant && lastAssistant.id > 0) {
      try {
        await chatApi.deleteMessage(lastAssistant.id)
      } catch {
        /* 删除失败也继续重新生成 */
      }
    }
    messages.value = messages.value.filter((item) => item !== lastAssistant)
    await sendMessage(content, { regenerate: Boolean(lastAssistant) })
  }

  /** 编辑用户消息并重新发送：删除该消息及其之后的所有消息 */
  async function editAndResend(message: ChatMessage, newContent: string) {
    if (streaming.value) {
      antMessage.warning('请先停止当前生成')
      return
    }
    const index = messages.value.findIndex((item) => item.id === message.id)
    if (index < 0) return
    const tail = messages.value.slice(index)
    for (const item of tail) {
      if (item.id > 0) {
        try {
          await chatApi.deleteMessage(item.id)
        } catch {
          /* 忽略单条删除失败 */
        }
      }
    }
    messages.value = messages.value.slice(0, index)
    await sendMessage(newContent)
  }

  function resetState() {
    currentId.value = null
    messages.value = []
    errorMessage.value = null
    notices.value = []
    currentRoute.value = null
  }

  return {
    conversations,
    currentId,
    messages,
    loadingConversations,
    loadingMessages,
    streaming,
    thinking,
    errorMessage,
    notices,
    lastUsage,
    currentRoute,
    currentConversation,
    hasMessages,
    favoriteConversations,
    fetchConversations,
    createConversation,
    selectConversation,
    loadMessages,
    renameConversation,
    toggleFavorite,
    archiveConversation,
    deleteConversation,
    clearCurrentConversation,
    sendMessage,
    stopGenerate,
    regenerate,
    resend,
    editAndResend,
    resetState,
  }
})
