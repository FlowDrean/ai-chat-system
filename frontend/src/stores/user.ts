/** 用户状态：登录态 / 当前用户 / 权限 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { authApi } from '@/api/auth'
import { clearToken, getToken, setToken } from '@/api/request'
import type { LoginPayload, RegisterPayload, UserInfo } from '@/types'

export const useUserStore = defineStore('user', () => {
  const token = ref<string>(getToken())
  const user = ref<UserInfo | null>(null)
  const loading = ref(false)
  const initialized = ref(false)

  const isLoggedIn = computed(() => Boolean(token.value))
  const isAdmin = computed(() => Boolean(user.value?.is_admin || user.value?.role === 'admin'))
  const displayName = computed(() => user.value?.nickname || user.value?.username || '未登录')
  const avatarText = computed(() => displayName.value.slice(0, 1).toUpperCase())

  function applyLogin(payload: { access_token: string; user: UserInfo }) {
    token.value = payload.access_token
    setToken(payload.access_token)
    user.value = payload.user
    initialized.value = true
  }

  async function login(payload: LoginPayload) {
    loading.value = true
    try {
      applyLogin(await authApi.login(payload))
      return user.value
    } finally {
      loading.value = false
    }
  }

  async function register(payload: RegisterPayload) {
    loading.value = true
    try {
      applyLogin(await authApi.register(payload))
      return user.value
    } finally {
      loading.value = false
    }
  }

  /** 应用启动时恢复登录态（有 token 才请求） */
  async function bootstrap() {
    if (!token.value) {
      initialized.value = true
      return
    }
    try {
      user.value = await authApi.me()
    } catch {
      logout()
    } finally {
      initialized.value = true
    }
  }

  async function refresh() {
    if (!token.value) return
    user.value = await authApi.me()
  }

  async function logout() {
    try {
      if (token.value) await authApi.logout()
    } catch {
      /* 忽略退出接口异常 */
    }
    token.value = ''
    user.value = null
    clearToken()
  }

  function updateProfile(patch: Partial<UserInfo>) {
    user.value = user.value ? { ...user.value, ...patch } : user.value
  }

  return {
    token,
    user,
    loading,
    initialized,
    isLoggedIn,
    isAdmin,
    displayName,
    avatarText,
    login,
    register,
    logout,
    bootstrap,
    refresh,
    updateProfile,
  }
})
