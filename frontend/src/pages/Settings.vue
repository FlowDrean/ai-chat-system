<template>
  <AdminLayout>
    <div class="page-container">
      <div class="page-header">
        <div>
          <h1 class="page-title">系统设置</h1>
          <p class="page-subtitle">个人资料、密码安全与系统运行信息。</p>
        </div>
      </div>

      <a-row :gutter="16">
        <a-col :xs="24" :lg="12">
          <a-card title="个人资料" size="small" :bordered="true">
            <a-form :model="profileForm" layout="vertical">
              <a-form-item label="用户名">
                <a-input :value="userStore.user?.username" disabled />
              </a-form-item>
              <a-form-item label="昵称">
                <a-input v-model:value="profileForm.nickname" placeholder="用于界面展示" />
              </a-form-item>
              <a-form-item label="邮箱">
                <a-input v-model:value="profileForm.email" placeholder="可选" />
              </a-form-item>
              <a-button type="primary" :loading="savingProfile" @click="saveProfile">保存资料</a-button>
            </a-form>
          </a-card>

          <a-card title="修改密码" size="small" :bordered="true" class="settings-card">
            <a-form :model="passwordForm" layout="vertical">
              <a-form-item label="当前密码">
                <a-input-password v-model:value="passwordForm.old_password" autocomplete="current-password" />
              </a-form-item>
              <a-form-item label="新密码">
                <a-input-password v-model:value="passwordForm.new_password" autocomplete="new-password" />
              </a-form-item>
              <a-form-item label="确认新密码">
                <a-input-password v-model:value="passwordForm.confirm" autocomplete="new-password" />
              </a-form-item>
              <a-button type="primary" :loading="savingPassword" @click="changePassword">修改密码</a-button>
            </a-form>
          </a-card>
        </a-col>

        <a-col :xs="24" :lg="12">
          <a-card title="界面偏好" size="small" :bordered="true">
            <div class="pref-row">
              <span>主题外观</span>
              <a-segmented v-model:value="themeMode" :options="themeOptions" size="small" />
            </div>
            <div class="pref-row">
              <span>展示 Token / 耗时</span>
              <a-switch v-model:checked="settings.showTokenUsage" />
            </div>
            <div class="pref-row">
              <span>默认自动使用知识库（RAG）</span>
              <a-switch v-model:checked="settings.autoRag" />
            </div>
            <div class="pref-row">
              <span>侧边栏默认收起</span>
              <a-switch v-model:checked="settings.sidebarCollapsed" />
            </div>
            <a-divider />
            <a-descriptions :column="1" size="small" title="默认会话参数">
              <a-descriptions-item label="Temperature">{{ settings.params.temperature }}</a-descriptions-item>
              <a-descriptions-item label="Top P">{{ settings.params.top_p }}</a-descriptions-item>
              <a-descriptions-item label="Max Tokens">{{ settings.params.max_tokens }}</a-descriptions-item>
            </a-descriptions>
            <a-button size="small" class="pref-reset" @click="settings.resetParams()">恢复默认参数</a-button>
          </a-card>

          <a-card v-if="userStore.isAdmin" title="系统信息" size="small" :bordered="true" class="settings-card">
            <a-spin :spinning="loadingInfo">
              <a-descriptions :column="1" size="small">
                <a-descriptions-item v-for="item in systemInfoItems" :key="item.label" :label="item.label">
                  {{ item.value }}
                </a-descriptions-item>
              </a-descriptions>
            </a-spin>
          </a-card>
        </a-col>
      </a-row>
    </div>
  </AdminLayout>
</template>

<script setup lang="ts">
/** 系统设置：个人资料 / 修改密码 / 界面偏好 / 系统信息 */
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'

import AdminLayout from '@/layouts/AdminLayout.vue'
import { authApi } from '@/api/auth'
import { dashboardApi } from '@/api/dashboard'
import { userApi } from '@/api/user'
import { useSettingsStore } from '@/stores/settings'
import { useThemeStore, type ThemeMode } from '@/stores/theme'
import { useUserStore } from '@/stores/user'

const userStore = useUserStore()
const settings = useSettingsStore()
const themeStore = useThemeStore()

const themeOptions = [
  { label: '亮色', value: 'light' },
  { label: '暗色', value: 'dark' },
  { label: '跟随系统', value: 'system' },
]

const themeMode = computed<ThemeMode>({
  get: () => themeStore.mode,
  set: (value) => themeStore.setMode(value),
})

const savingProfile = ref(false)
const savingPassword = ref(false)
const loadingInfo = ref(false)
const systemInfo = ref<Record<string, unknown>>({})

const profileForm = reactive({
  nickname: userStore.user?.nickname || '',
  email: userStore.user?.email || '',
})

const passwordForm = reactive({ old_password: '', new_password: '', confirm: '' })

const systemInfoItems = computed(() =>
  Object.entries(systemInfo.value).map(([key, value]) => ({
    label: key,
    value: Array.isArray(value) ? value.join(', ') : String(value),
  })),
)

async function saveProfile() {
  savingProfile.value = true
  try {
    await userApi.updateProfile({ nickname: profileForm.nickname, email: profileForm.email })
    await userStore.refresh()
    message.success('资料已更新')
  } finally {
    savingProfile.value = false
  }
}

async function changePassword() {
  if (!passwordForm.old_password || !passwordForm.new_password) {
    message.warning('请填写完整')
    return
  }
  if (passwordForm.new_password !== passwordForm.confirm) {
    message.warning('两次输入的新密码不一致')
    return
  }
  if (passwordForm.new_password.length < 6) {
    message.warning('新密码至少 6 位')
    return
  }
  savingPassword.value = true
  try {
    await authApi.changePassword({
      old_password: passwordForm.old_password,
      new_password: passwordForm.new_password,
    })
    message.success('密码修改成功，请重新登录')
    passwordForm.old_password = ''
    passwordForm.new_password = ''
    passwordForm.confirm = ''
    setTimeout(async () => {
      await userStore.logout()
      location.href = '/login'
    }, 800)
  } finally {
    savingPassword.value = false
  }
}

onMounted(async () => {
  if (!userStore.user) await userStore.refresh().catch(() => undefined)
  profileForm.nickname = userStore.user?.nickname || ''
  profileForm.email = userStore.user?.email || ''
  if (userStore.isAdmin) {
    loadingInfo.value = true
    try {
      systemInfo.value = await dashboardApi.systemInfo()
    } finally {
      loadingInfo.value = false
    }
  }
})
</script>

<style scoped>
.settings-card {
  margin-top: 16px;
}

.pref-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 0;
  font-size: 13px;
}

.pref-reset {
  margin-top: 12px;
}
</style>
