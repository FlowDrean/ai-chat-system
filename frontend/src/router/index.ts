/** 路由配置 + 登录 / 权限守卫 */
import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

import ChatLayout from '@/layouts/ChatLayout.vue'
import { getToken } from '@/api/request'
import { useUserStore } from '@/stores/user'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: () => import('@/pages/Login.vue'),
    meta: { title: '登录', public: true },
  },
  {
    path: '/',
    name: 'home',
    component: () => import('@/pages/Home.vue'),
    meta: { title: '首页' },
  },
  {
    path: '/chat',
    name: 'chat',
    component: () => import('@/pages/Chat.vue'),
    meta: { title: 'AI 聊天' },
  },
  {
    path: '/admin',
    redirect: '/admin/dashboard',
    meta: { title: '管理后台' },
  },
  {
    path: '/admin/dashboard',
    name: 'admin-dashboard',
    component: () => import('@/pages/Dashboard.vue'),
    meta: { title: 'Dashboard' },
  },
  {
    path: '/admin/models',
    name: 'admin-models',
    component: () => import('@/pages/Model.vue'),
    meta: { title: '模型管理', admin: true },
  },
  {
    path: '/admin/knowledge',
    name: 'admin-knowledge',
    component: () => import('@/pages/Knowledge.vue'),
    meta: { title: '知识库' },
  },
  {
    path: '/admin/knowledge/:id(\\d+)',
    name: 'admin-knowledge-detail',
    component: () => import('@/pages/KnowledgeDetail.vue'),
    meta: { title: '知识库详情' },
  },
  {
    path: '/admin/documents',
    name: 'admin-documents',
    component: () => import('@/pages/Documents.vue'),
    meta: { title: '文档管理' },
  },
  {
    path: '/admin/mcp',
    name: 'admin-mcp',
    component: () => import('@/pages/Mcp.vue'),
    meta: { title: 'MCP 管理' },
  },
  {
    path: '/admin/skills',
    name: 'admin-skills',
    component: () => import('@/pages/Skill.vue'),
    meta: { title: '技能管理' },
  },
  {
    path: '/admin/prompts',
    name: 'admin-prompts',
    component: () => import('@/pages/Prompt.vue'),
    meta: { title: 'Prompt 管理' },
  },
  {
    path: '/admin/users',
    name: 'admin-users',
    component: () => import('@/pages/Users.vue'),
    meta: { title: '用户管理', admin: true },
  },
  {
    path: '/admin/settings',
    name: 'admin-settings',
    component: () => import('@/pages/Settings.vue'),
    meta: { title: '系统设置' },
  },
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/pages/NotFound.vue'),
    meta: { title: '页面不存在', public: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async (to) => {
  const token = getToken()
  const title = (to.meta.title as string) || 'AI Assistant'
  document.title = `${title} · AI Assistant`

  // 未登录 → 跳登录页
  if (!to.meta.public && !token) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }

  // 已登录访问登录页 → 回首页
  if (to.path === '/login' && token) {
    return { path: '/' }
  }

  // 管理员页面校验
  if (to.meta.admin) {
    const userStore = useUserStore()
    if (!userStore.user) await userStore.bootstrap().catch(() => undefined)
    if (!userStore.isAdmin) {
      return { path: '/chat' }
    }
  }

  return true
})

export { ChatLayout }
export default router
