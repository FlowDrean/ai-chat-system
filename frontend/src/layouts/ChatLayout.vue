<template>
  <div class="chat-layout">
    <!-- 侧边栏（移动端为抽屉） -->
    <aside v-if="!isMobile" class="chat-layout__sider" :class="{ collapsed }">
      <!-- 折叠态：隐藏 logo，只保留居中的「展开」按钮，整行也可点击展开 -->
      <div
        class="chat-layout__brand"
        :class="{ 'is-collapsed': collapsed }"
        @click="!isMobile && collapsed && toggleCollapse()"
      >
        <AppLogo v-if="!collapsed" class="chat-layout__logo" />
        <a-tooltip :title="collapsed ? '展开侧边栏' : '收起侧边栏'" placement="right">
          <button
            type="button"
            class="chat-layout__collapse"
            :aria-label="collapsed ? '展开侧边栏' : '收起侧边栏'"
            @click.stop="toggleCollapse"
          >
            <MenuFoldOutlined v-if="!collapsed" />
            <MenuUnfoldOutlined v-else />
          </button>
        </a-tooltip>
      </div>

      <div v-if="!collapsed" class="chat-layout__list">
        <slot name="sidebar">
          <ConversationList
            :conversations="chatStore.conversations"
            :active-id="chatStore.currentId"
            :loading="chatStore.loadingConversations"
            @create="handleCreate"
            @select="handleSelect"
            @rename="handleRename"
            @favorite="handleFavorite"
            @archive="handleArchive"
            @delete="handleDelete"
          />
        </slot>
      </div>
      <div v-else class="chat-layout__mini">
        <a-tooltip title="新建聊天" placement="right">
          <button type="button" class="chat-layout__mini-btn" @click="handleCreate">
            <PlusOutlined />
          </button>
        </a-tooltip>
        <a-tooltip v-for="item in chatStore.conversations.slice(0, 8)" :key="item.id" :title="item.title" placement="right">
          <button
            type="button"
            class="chat-layout__mini-btn"
            :class="{ active: item.id === chatStore.currentId }"
            @click="handleSelect(item.id)"
          >
            <MessageOutlined />
          </button>
        </a-tooltip>
      </div>

      <div class="chat-layout__footer">
        <a-dropdown :trigger="['click']" placement="topRight">
          <div class="chat-layout__user">
            <a-avatar :size="28" :style="{ background: 'var(--brand)', color: 'var(--brand-contrast)' }">{{ userStore.avatarText }}</a-avatar>
            <div v-if="!collapsed" class="chat-layout__user-info">
              <span class="text-ellipsis">{{ userStore.displayName }}</span>
              <small>{{ userStore.isAdmin ? '管理员' : '普通用户' }}</small>
            </div>
          </div>
          <template #overlay>
            <a-menu @click="(info: MenuInfo) => handleUserAction(String(info.key))">
              <a-menu-item key="home"><HomeOutlined /> 首页</a-menu-item>
              <a-menu-item key="admin"><SettingOutlined /> 管理后台</a-menu-item>
              <a-menu-divider />
              <a-menu-item key="logout"><LogoutOutlined /> 退出登录</a-menu-item>
            </a-menu>
          </template>
        </a-dropdown>
      </div>
    </aside>

    <!-- 移动端抽屉 -->
    <a-drawer
      v-if="isMobile"
      :open="settings.mobileSidebarOpen"
      placement="left"
      :width="286"
      :body-style="{ padding: 0 }"
      :closable="false"
      @close="settings.mobileSidebarOpen = false"
    >
      <div class="chat-layout__drawer-body">
        <div class="chat-layout__brand is-drawer">
          <AppLogo />
          <button
            type="button"
            class="chat-layout__collapse"
            aria-label="关闭会话列表"
            @click="settings.mobileSidebarOpen = false"
          >
            <CloseOutlined />
          </button>
        </div>
        <div class="chat-layout__list">
          <ConversationList
            :conversations="chatStore.conversations"
            :active-id="chatStore.currentId"
            :loading="chatStore.loadingConversations"
            @create="
              () => {
                handleCreate()
                settings.mobileSidebarOpen = false
              }
            "
            @select="
              (id) => {
                handleSelect(id)
                settings.mobileSidebarOpen = false
              }
            "
            @rename="handleRename"
            @favorite="handleFavorite"
            @archive="handleArchive"
            @delete="handleDelete"
          />
        </div>
        <div class="chat-layout__footer">
          <div class="chat-layout__user" @click="settings.mobileSidebarOpen = false">
            <a-avatar :size="28" :style="{ background: 'var(--brand)', color: 'var(--brand-contrast)' }">{{ userStore.avatarText }}</a-avatar>
            <div class="chat-layout__user-info">
              <span class="text-ellipsis">{{ userStore.displayName }}</span>
              <small>{{ userStore.isAdmin ? '管理员' : '普通用户' }}</small>
            </div>
          </div>
        </div>
      </div>
    </a-drawer>

    <!-- 主内容 -->
    <main class="chat-layout__main">
      <slot />
    </main>

    <!-- 移动端：会话列表入口在顶部导航（chat-header 的菜单按钮），
         这里只保留一个「新建聊天」浮动按钮，并抬高到输入区之上避免遮挡 -->
    <a-float-button
      v-if="isMobile"
      type="primary"
      aria-label="新建聊天"
      class="chat-layout__fab"
      :style="{ right: '16px', bottom: '132px', zIndex: 20 }"
      @click="handleCreate"
    >
      <template #icon><PlusOutlined /></template>
    </a-float-button>
  </div>
</template>

<script setup lang="ts">
/** 聊天布局：左侧会话列表 + 右侧内容区（移动端抽屉式） */
import { computed, onMounted } from 'vue'
import { Modal } from 'ant-design-vue'
import {
  HomeOutlined,
  CloseOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MessageOutlined,
  PlusOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import { useRouter } from 'vue-router'

import AppLogo from '@/components/common/AppLogo.vue'
import ConversationList from '@/components/chat/ConversationList.vue'
import { useChatStore } from '@/stores/chat'
import { useSettingsStore } from '@/stores/settings'
import { useUserStore } from '@/stores/user'
import { useMediaQuery } from '@vueuse/core'
import type { Conversation } from '@/types'
import type { MenuInfo } from 'ant-design-vue/es/menu/src/interface'

const router = useRouter()
const chatStore = useChatStore()
const userStore = useUserStore()
const settings = useSettingsStore()

const isMobile = useMediaQuery('(max-width: 992px)')
const collapsed = computed({
  get: () => settings.sidebarCollapsed,
  set: (value: boolean) => (settings.sidebarCollapsed = value),
})

onMounted(() => {
  chatStore.fetchConversations().catch(() => undefined)
})

function toggleCollapse() {
  collapsed.value = !collapsed.value
}

async function handleCreate() {
  chatStore.resetState()
  if (router.currentRoute.value.path !== '/chat') {
    await router.push('/chat')
  }
}

async function handleSelect(id: number) {
  await router.push('/chat')
  chatStore.selectConversation(id).catch(() => undefined)
}

function handleRename(payload: { id: number; title: string }) {
  chatStore.renameConversation(payload.id, payload.title).catch(() => undefined)
}

function handleFavorite(conversation: Conversation) {
  chatStore.toggleFavorite(conversation).catch(() => undefined)
}

function handleArchive(conversation: Conversation) {
  chatStore.archiveConversation(conversation).catch(() => undefined)
}

function handleDelete(conversation: Conversation) {
  chatStore.deleteConversation(conversation.id).catch(() => undefined)
}

async function handleUserAction(key: string) {
  if (key === 'home') await router.push('/')
  else if (key === 'admin') await router.push('/admin/dashboard')
  else if (key === 'logout') {
    Modal.confirm({
      title: '退出登录',
      content: '确定要退出当前账号吗？',
      okText: '退出',
      cancelText: '取消',
      onOk: async () => {
        await userStore.logout()
        await router.push('/login')
      },
    })
  }
}
</script>

<style scoped>
.chat-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--bg-page);
}

.chat-layout__sider {
  display: flex;
  flex-direction: column;
  width: 272px;
  flex-shrink: 0;
  background: var(--bg-card);
  border-right: 1px solid var(--border-color);
  transition: width var(--transition);
  /* 兜底：侧边栏内的任何内容都不得溢出到聊天区 */
  overflow: hidden;
}

.chat-layout__sider.collapsed {
  width: 64px;
}

.chat-layout__brand {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  height: var(--header-height);
  padding: 0 12px;
  border-bottom: 1px solid var(--border-color);
  /* 关键：容器很窄（折叠后仅 64px），必须禁止内容溢出，
     否则按钮会被挤出侧边栏并被右侧聊天区盖住 */
  overflow: hidden;
  flex-shrink: 0;
}

/* 折叠态：只显示居中的展开按钮，整行都可点击 */
.chat-layout__brand.is-collapsed {
  justify-content: center;
  padding: 0;
  cursor: pointer;
}

/* 抽屉内的顶部条：正常左右分布（宽度足够，不存在溢出问题） */
.chat-layout__brand.is-drawer {
  padding: 0 12px;
}

.chat-layout__brand.is-collapsed:hover {
  background: var(--bg-hover);
}

.chat-layout__logo {
  min-width: 0;
}

.chat-layout__collapse {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 15px;
  transition: var(--transition);
}

.chat-layout__collapse:hover {
  background: var(--bg-hover);
  color: var(--brand);
}

/* 折叠态下按钮就是该行的唯一元素，hover 背景已整行高亮，避免重复底色 */
.chat-layout__brand.is-collapsed .chat-layout__collapse:hover {
  background: transparent;
  color: var(--brand);
}

.chat-layout__list {
  flex: 1;
  min-height: 0;
}

.chat-layout__mini {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  padding: 12px 0;
  flex: 1;
  overflow-y: auto;
}

.chat-layout__mini-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 9px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: var(--transition);
}

.chat-layout__mini-btn:hover,
.chat-layout__mini-btn.active {
  background: var(--brand-soft);
  color: var(--brand);
}

.chat-layout__footer {
  padding: 10px 12px;
  border-top: 1px solid var(--border-color);
}

.chat-layout__user {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px;
  border-radius: 8px;
  cursor: pointer;
  min-width: 0;
}

.chat-layout__user:hover {
  background: var(--bg-hover);
}

.chat-layout__user-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
  line-height: 1.25;
}

.chat-layout__user-info span {
  font-size: 13px;
  font-weight: 500;
}

.chat-layout__user-info small {
  font-size: 11px;
  color: var(--text-secondary);
}

.chat-layout__main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-layout__drawer-body {
  display: flex;
  flex-direction: column;
  height: 100%;
}
</style>
