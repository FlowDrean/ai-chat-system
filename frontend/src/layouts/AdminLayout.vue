<template>
  <a-layout class="admin-layout">
    <a-layout-sider
      v-model:collapsed="collapsed"
      :trigger="null"
      collapsible
      :width="216"
      class="admin-layout__sider"
      :class="{ 'is-mobile': isMobile }"
      :breakpoint="'lg'"
    >
      <div class="admin-layout__brand">
        <AppLogo :compact="collapsed" />
      </div>
      <a-menu
        v-model:selectedKeys="selectedKeys"
        mode="inline"
        class="admin-layout__menu"
        @click="handleMenuClick"
      >
        <a-menu-item key="/admin/dashboard">
          <template #icon><DashboardOutlined /></template>
          <span>Dashboard</span>
        </a-menu-item>
        <a-menu-item key="/admin/models">
          <template #icon><DeploymentUnitOutlined /></template>
          <span>模型管理</span>
        </a-menu-item>
        <a-menu-item key="/admin/knowledge">
          <template #icon><DatabaseOutlined /></template>
          <span>知识库</span>
        </a-menu-item>
        <a-menu-item key="/admin/documents">
          <template #icon><FileTextOutlined /></template>
          <span>文档管理</span>
        </a-menu-item>
        <a-menu-item key="/admin/mcp">
          <template #icon><ApiOutlined /></template>
          <span>MCP 管理</span>
        </a-menu-item>
        <a-menu-item key="/admin/skills">
          <template #icon><ThunderboltOutlined /></template>
          <span>技能管理</span>
        </a-menu-item>
        <a-menu-item key="/admin/prompts">
          <template #icon><BulbOutlined /></template>
          <span>Prompt 管理</span>
        </a-menu-item>
        <a-menu-item v-if="userStore.isAdmin" key="/admin/users">
          <template #icon><TeamOutlined /></template>
          <span>用户管理</span>
        </a-menu-item>
        <a-menu-item key="/admin/settings">
          <template #icon><SettingOutlined /></template>
          <span>系统设置</span>
        </a-menu-item>
      </a-menu>
    </a-layout-sider>

    <a-layout>
      <a-layout-header class="admin-layout__header">
        <div class="admin-layout__header-left">
          <button type="button" class="admin-layout__icon-btn" @click="collapsed = !collapsed">
            <MenuFoldOutlined v-if="!collapsed" />
            <MenuUnfoldOutlined v-else />
          </button>
          <h2 class="admin-layout__title">{{ pageTitle }}</h2>
        </div>

        <div class="admin-layout__header-right">
          <ThemeToggle />
          <a-tooltip title="返回聊天">
            <a-button type="text" @click="router.push('/chat')">
              <template #icon><MessageOutlined /></template>
              去聊天
            </a-button>
          </a-tooltip>
          <a-dropdown :trigger="['click']" placement="bottomRight">
            <div class="admin-layout__user">
              <a-avatar :size="28" :style="{ background: 'var(--brand)', color: 'var(--brand-contrast)' }">{{ userStore.avatarText }}</a-avatar>
              <span class="admin-layout__user-name">{{ userStore.displayName }}</span>
            </div>
            <template #overlay>
              <a-menu @click="(info: MenuInfo) => handleUserAction(String(info.key))">
                <a-menu-item key="profile"><UserOutlined /> 个人中心</a-menu-item>
                <a-menu-item key="chat"><MessageOutlined /> 返回聊天</a-menu-item>
                <a-menu-divider />
                <a-menu-item key="logout" danger><LogoutOutlined /> 退出登录</a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
      </a-layout-header>

      <a-layout-content class="admin-layout__content">
        <!-- 各页面以 <AdminLayout>...</AdminLayout> 的方式包裹本布局，
             因此这里使用 slot 而不是 router-view，避免路由视图递归嵌套 -->
        <slot />
      </a-layout-content>
    </a-layout>
  </a-layout>
</template>

<script setup lang="ts">
/** 管理后台布局：左侧菜单 + 顶部栏 + 内容区 */
import { computed, onMounted, ref, watch } from 'vue'
import { Modal } from 'ant-design-vue'
import {
  ApiOutlined,
  BulbOutlined,
  DashboardOutlined,
  DatabaseOutlined,
  DeploymentUnitOutlined,
  FileTextOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  MessageOutlined,
  SettingOutlined,
  TeamOutlined,
  ThunderboltOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import { useMediaQuery } from '@vueuse/core'

import AppLogo from '@/components/common/AppLogo.vue'
import ThemeToggle from '@/components/common/ThemeToggle.vue'
import { useUserStore } from '@/stores/user'
import type { MenuInfo } from 'ant-design-vue/es/menu/src/interface'


const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const isMobile = useMediaQuery('(max-width: 992px)')

// 模块级状态：页面切换后仍然保持侧边栏收起状态
const collapsed = ref(localStorage.getItem('ai_chat_admin_collapsed') === '1')
watch(collapsed, (value) => localStorage.setItem('ai_chat_admin_collapsed', value ? '1' : '0'))

const selectedKeys = computed(() => [route.path])
const pageTitle = computed(() => (route.meta.title as string) || '管理后台')

watch(isMobile, (mobile) => {
  collapsed.value = mobile
}, { immediate: true })

onMounted(() => {
  userStore.refresh().catch(() => undefined)
})

function handleMenuClick(info: { key: string | number }) {
  router.push(String(info.key))
}

async function handleUserAction(key: string) {
  if (key === 'profile') await router.push('/admin/settings')
  else if (key === 'chat') await router.push('/chat')
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
.admin-layout {
  min-height: 100vh;
}

.admin-layout__sider {
  background: var(--bg-card);
  border-right: 1px solid var(--border-color);
}

.admin-layout__brand {
  display: flex;
  align-items: center;
  height: var(--header-height);
  padding: 0 16px;
  border-bottom: 1px solid var(--border-color);
}

.admin-layout__menu {
  border-inline-end: none !important;
  padding: 8px 6px;
  background: transparent;
}

/* ---------------------------------------------------------------------------
 * 侧栏导航（dock）选中态：反白药丸  黑底白字
 *
 * 主渠道是 App.vue 的 components.Menu（colorItemBgSelected / colorItemTextSelected）；
 * 这里再用 :deep() 兜一层，保证即使 antd 内部 token 变化，也不会退回「灰底黑字」。
 * 必须用 :deep()：antd 渲染出的 li 上没有 scoped 的 data-v 属性。
 * ------------------------------------------------------------------------- */
.admin-layout__menu :deep(.ant-menu-item) {
  transition: background var(--transition), color var(--transition);
}

.admin-layout__menu :deep(.ant-menu-item:not(.ant-menu-item-selected):hover) {
  background: var(--bg-hover) !important;
  color: var(--text-primary) !important;
}

.admin-layout__menu :deep(.ant-menu-item-selected),
.admin-layout__menu :deep(.ant-menu-item-selected:hover),
.admin-layout__menu :deep(.ant-menu-item-selected:active) {
  background: var(--brand) !important;
  color: var(--brand-contrast) !important;
  font-weight: 500;
}

.admin-layout__menu :deep(.ant-menu-item-selected .ant-menu-item-icon),
.admin-layout__menu :deep(.ant-menu-item-selected .anticon),
.admin-layout__menu :deep(.ant-menu-item-selected svg) {
  color: var(--brand-contrast) !important;
}

.admin-layout__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: var(--header-height);
  padding: 0 16px;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border-color);
  line-height: normal;
}

.admin-layout__header-left,
.admin-layout__header-right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.admin-layout__icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font-size: 15px;
}

.admin-layout__icon-btn:hover {
  background: var(--bg-hover);
  color: var(--brand);
}

.admin-layout__title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.admin-layout__user {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  border-radius: 8px;
  cursor: pointer;
}

.admin-layout__user:hover {
  background: var(--bg-hover);
}

.admin-layout__user-name {
  font-size: 13px;
}

.admin-layout__content {
  overflow-y: auto;
  background: var(--bg-page);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 160ms ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

@media (max-width: 768px) {
  .admin-layout__user-name {
    display: none;
  }
}
</style>
