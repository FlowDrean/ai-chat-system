<template>
  <ChatLayout>
    <div class="home-page">
      <div class="home-page__inner">
        <!-- 欢迎区 -->
        <header class="home-page__hero fade-in">
          <a-avatar :size="46" :style="{ background: 'var(--brand)', color: 'var(--brand-contrast)', fontSize: '20px' }">
            {{ userStore.avatarText }}
          </a-avatar>
          <div>
            <h1 class="home-page__greeting">你好，{{ userStore.displayName }}</h1>
            <p class="home-page__sub">我是 AI Assistant，有什么可以帮你？</p>
          </div>
        </header>

        <div class="home-page__cta">
          <a-button type="primary" size="large" @click="startChat()">
            <template #icon><PlusOutlined /></template>
            新建聊天
          </a-button>
          <a-input
            v-model:value="quickQuestion"
            class="home-page__quick-input"
            size="large"
            placeholder="直接提问，例如：用 Python 写一个 FastAPI 的 Hello World"
            @press-enter="startChat(quickQuestion)"
          />
        </div>

        <!-- 常用功能 -->
        <h3 class="home-page__section-title">常用功能</h3>
        <div class="home-page__features">
          <button
            v-for="item in features"
            :key="item.title"
            type="button"
            class="feature-card"
            @click="router.push(item.path)"
          >
            <span class="feature-card__icon">
              <component :is="item.icon" />
            </span>
            <div class="feature-card__body">
              <strong>{{ item.title }}</strong>
              <p>{{ item.desc }}</p>
            </div>
            <RightOutlined class="feature-card__arrow" />
          </button>
        </div>

        <!-- 概览 + 最近会话 -->
        <div class="home-page__grid">
          <a-card title="使用概览" :bordered="true" size="small" class="home-page__card">
            <template #extra>
              <a-button type="link" size="small" @click="router.push('/admin/dashboard')">
                更多统计
              </a-button>
            </template>
            <a-spin :spinning="loadingStats">
              <div class="home-page__stats">
                <div v-for="stat in statItems" :key="stat.label" class="home-page__stat">
                  <span class="home-page__stat-value">{{ stat.value }}</span>
                  <span class="home-page__stat-label">{{ stat.label }}</span>
                </div>
              </div>
            </a-spin>
          </a-card>

          <a-card title="最近会话" :bordered="true" size="small" class="home-page__card">
            <template #extra>
              <a-button type="link" size="small" @click="router.push('/chat')">全部会话</a-button>
            </template>
            <EmptyState
              v-if="!chatStore.conversations.length"
              :icon="MessageOutlined"
              title="还没有聊天记录"
              description="开始你的第一次 AI 对话吧。"
            >
              <a-button type="primary" size="small" @click="startChat()">开始聊天</a-button>
            </EmptyState>
            <ul v-else class="home-page__recent">
              <li v-for="item in chatStore.conversations.slice(0, 6)" :key="item.id" @click="openConversation(item.id)">
                <MessageOutlined class="home-page__recent-icon" />
                <span class="text-ellipsis">{{ item.title }}</span>
                <small>{{ formatRelative(item.updated_at) }}</small>
              </li>
            </ul>
          </a-card>
        </div>
      </div>
    </div>
  </ChatLayout>
</template>

<script setup lang="ts">
/** 首页：AI 产品 Dashboard 风格 —— 欢迎语 / 快速提问 / 常用功能 / 概览 */
import { computed, onMounted, ref } from 'vue'
import { message as antMessage } from 'ant-design-vue'
import {
  ApiOutlined,
  BulbOutlined,
  DatabaseOutlined,
  DeploymentUnitOutlined,
  MessageOutlined,
  PlusOutlined,
  RightOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons-vue'
import { useRouter } from 'vue-router'

import ChatLayout from '@/layouts/ChatLayout.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import { dashboardApi } from '@/api/dashboard'
import { useChatStore } from '@/stores/chat'
import { useUserStore } from '@/stores/user'
import type { DashboardStats } from '@/types'
import { formatNumber, formatRelative } from '@/utils/format'

const router = useRouter()
const userStore = useUserStore()
const chatStore = useChatStore()

const quickQuestion = ref('')
const loadingStats = ref(false)
const stats = ref<DashboardStats | null>(null)

const features = [
  {
    title: 'AI 对话',
    desc: '与 AI 交流，支持多模型、多轮上下文与流式输出',
    icon: MessageOutlined,
    path: '/chat',
  },
  {
    title: 'RAG 知识库',
    desc: '上传自己的资料，让 AI 基于你的知识库回答并给出引用',
    icon: DatabaseOutlined,
    path: '/admin/knowledge',
  },
  {
    title: '模型管理',
    desc: '配置 OpenAI / DeepSeek / 通义 / Ollama 等模型',
    icon: DeploymentUnitOutlined,
    path: '/admin/models',
  },
  {
    title: 'MCP 管理',
    desc: '接入 Model Context Protocol 服务，复用其工具能力',
    icon: ApiOutlined,
    path: '/admin/mcp',
  },
  {
    title: '技能管理',
    desc: '为 AI 配置可调用的能力：计算、时间、联网搜索、自定义接口',
    icon: ThunderboltOutlined,
    path: '/admin/skills',
  },
  {
    title: 'Prompt 管理',
    desc: '沉淀 System Prompt 模板，一键应用到对话',
    icon: BulbOutlined,
    path: '/admin/prompts',
  },
]

const statItems = computed(() => [
  { label: '会话总数', value: formatNumber(stats.value?.total_conversations ?? 0) },
  { label: '消息总数', value: formatNumber(stats.value?.total_messages ?? 0) },
  { label: 'Token 消耗', value: formatNumber(stats.value?.total_tokens ?? 0) },
  { label: '知识库', value: formatNumber(stats.value?.knowledge_base_count ?? 0) },
  { label: '文档', value: formatNumber(stats.value?.document_count ?? 0) },
  { label: '可用模型', value: formatNumber(stats.value?.enabled_model_count ?? 0) },
])

onMounted(async () => {
  chatStore.fetchConversations().catch(() => undefined)
  loadingStats.value = true
  try {
    const data = await dashboardApi.overview(7)
    stats.value = data.stats
  } catch {
    /* 首页统计失败不影响使用 */
  } finally {
    loadingStats.value = false
  }
})

async function startChat(question?: string) {
  const text = (question || '').trim()
  chatStore.resetState()
  await router.push('/chat')
  if (text) {
    chatStore.sendMessage(text).catch(() => antMessage.error('发送失败，请重试'))
  }
}

async function openConversation(id: number) {
  await router.push('/chat')
  chatStore.selectConversation(id).catch(() => undefined)
}
</script>

<style scoped>
.home-page {
  flex: 1;
  overflow-y: auto;
  background: var(--bg-page);
}

.home-page__inner {
  max-width: 980px;
  margin: 0 auto;
  padding: 40px 24px 60px;
}

.home-page__hero {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 24px;
}

.home-page__greeting {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
}

.home-page__sub {
  margin: 2px 0 0;
  font-size: 14px;
  color: var(--text-secondary);
}

.home-page__cta {
  display: flex;
  gap: 12px;
  margin-bottom: 36px;
  flex-wrap: wrap;
}

.home-page__quick-input {
  flex: 1;
  min-width: 260px;
}

.home-page__section-title {
  margin: 0 0 14px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}

.home-page__features {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 14px;
  margin-bottom: 36px;
}

.feature-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  text-align: left;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  cursor: pointer;
  transition: var(--transition);
}

.feature-card:hover {
  border-color: var(--border-dark);
  box-shadow: var(--shadow-pop);
  transform: translateY(-1px);
}

.feature-card__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  border-radius: 10px;
  font-size: 18px;
  flex-shrink: 0;
}

.feature-card__body {
  flex: 1;
  min-width: 0;
}

.feature-card__body strong {
  display: block;
  font-size: 14px;
}

.feature-card__body p {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.feature-card__arrow {
  color: var(--text-tertiary);
}

.home-page__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
}

.home-page__stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px 8px;
}

.home-page__stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.home-page__stat-value {
  font-size: 20px;
  font-weight: 600;
}

.home-page__stat-label {
  font-size: 12px;
  color: var(--text-secondary);
}

.home-page__recent {
  list-style: none;
  margin: 0;
  padding: 0;
}

.home-page__recent li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 6px;
  border-radius: 8px;
  cursor: pointer;
  transition: background var(--transition);
}

.home-page__recent li:hover {
  background: var(--bg-hover);
}

.home-page__recent-icon {
  color: var(--brand);
}

.home-page__recent span {
  flex: 1;
  min-width: 0;
  font-size: 13px;
}

.home-page__recent small {
  font-size: 11px;
  color: var(--text-tertiary);
}
</style>
