/** 设置状态：会话级模型参数 / 默认选择 / UI 偏好（持久化到 localStorage） */
import { defineStore } from 'pinia'
import { ref, watch } from 'vue'

import type { ChatParams } from '@/types'

const STORAGE_KEY = 'ai_chat_settings'

interface PersistedState {
  modelId: number | null
  knowledgeBaseId: number | null
  promptId: number | null
  skillIds: number[]
  mcpServerIds: number[]
  params: ChatParams
  sidebarCollapsed: boolean
  showTokenUsage: boolean
  autoRag: boolean
}

function load(): PersistedState {
  const fallback: PersistedState = {
    modelId: null,
    knowledgeBaseId: null,
    promptId: null,
    skillIds: [],
    mcpServerIds: [],
    params: {
      temperature: 0.7,
      top_p: 1,
      max_tokens: 4096,
      frequency_penalty: 0,
      presence_penalty: 0,
      streaming: true,
    },
    sidebarCollapsed: false,
    showTokenUsage: true,
    autoRag: true,
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return fallback
    const parsed = JSON.parse(raw) as Partial<PersistedState>
    return { ...fallback, ...parsed, params: { ...fallback.params, ...(parsed.params || {}) } }
  } catch {
    return fallback
  }
}

export const useSettingsStore = defineStore('settings', () => {
  const state = load()

  const modelId = ref<number | null>(state.modelId)
  const knowledgeBaseId = ref<number | null>(state.knowledgeBaseId)
  const promptId = ref<number | null>(state.promptId)
  /** 聊天时选中的技能（会同步到会话上） */
  const skillIds = ref<number[]>(state.skillIds || [])
  /** 聊天时选中的 MCP 服务（会同步到会话上） */
  const mcpServerIds = ref<number[]>(state.mcpServerIds || [])
  const params = ref<ChatParams>(state.params)
  const sidebarCollapsed = ref(state.sidebarCollapsed)
  // 移动端会话抽屉开关：纯运行时状态，不需要持久化
  const mobileSidebarOpen = ref(false)
  const showTokenUsage = ref(state.showTokenUsage)
  const autoRag = ref(state.autoRag)

  function persist() {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        modelId: modelId.value,
        knowledgeBaseId: knowledgeBaseId.value,
        promptId: promptId.value,
        skillIds: skillIds.value,
        mcpServerIds: mcpServerIds.value,
        params: params.value,
        sidebarCollapsed: sidebarCollapsed.value,
        showTokenUsage: showTokenUsage.value,
        autoRag: autoRag.value,
      }),
    )
  }

  watch(
    [modelId, knowledgeBaseId, promptId, skillIds, mcpServerIds, params, sidebarCollapsed, showTokenUsage, autoRag],
    persist,
    { deep: true },
  )

  function resetParams() {
    params.value = {
      temperature: 0.7,
      top_p: 1,
      max_tokens: 4096,
      frequency_penalty: 0,
      presence_penalty: 0,
      streaming: true,
    }
  }

  return {
    modelId,
    knowledgeBaseId,
    promptId,
    skillIds,
    mcpServerIds,
    params,
    sidebarCollapsed,
    mobileSidebarOpen,
    showTokenUsage,
    autoRag,
    resetParams,
    persist,
  }
})
