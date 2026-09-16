<template>
  <AdminLayout>
    <div class="page-container">
      <div class="page-header">
        <div>
          <h1 class="page-title">用户管理</h1>
          <p class="page-subtitle">管理系统用户、角色与状态（管理员专属）。</p>
        </div>
        <a-space>
          <a-input
            v-model:value="filters.keyword"
            placeholder="用户名 / 邮箱 / 昵称"
            allow-clear
            style="width: 220px"
            @press-enter="load"
          >
            <template #prefix><SearchOutlined /></template>
          </a-input>
          <a-select
            v-model:value="filters.role"
            :options="[
              { value: 'user', label: '普通用户' },
              { value: 'admin', label: '管理员' },
            ]"
            placeholder="全部角色"
            allow-clear
            style="width: 140px"
            @change="load"
          />
          <a-button @click="load">
            <template #icon><ReloadOutlined /></template>
          </a-button>
          <a-button type="primary" @click="openCreate">
            <template #icon><UserAddOutlined /></template>
            新建用户
          </a-button>
        </a-space>
      </div>

      <a-card :bordered="true" size="small">
        <LoadingView v-if="loading && !users.length" text="加载用户中…" />

        <a-table
          v-else
          :data-source="users"
          :columns="columns"
          :loading="loading"
          :pagination="paginationConfig"
          row-key="id"
          size="middle"
          @change="handleTableChange"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'username'">
              <div class="user-cell">
                <a-avatar :size="30" :style="{ background: 'var(--brand)', color: 'var(--brand-contrast)' }">
                  {{ (record.nickname || record.username).slice(0, 1).toUpperCase() }}
                </a-avatar>
                <div class="user-cell__info">
                  <span>{{ record.nickname || record.username }}</span>
                  <small>{{ record.username }}</small>
                </div>
              </div>
            </template>

            <template v-else-if="column.key === 'email'">{{ record.email || '-' }}</template>

            <template v-else-if="column.key === 'role'">
              <a-tag class="tag-mono" :class="{ 'is-strong': record.role === 'admin' }">
                {{ record.role === 'admin' ? '管理员' : '普通用户' }}
              </a-tag>
            </template>

            <template v-else-if="column.key === 'status'">
              <a-badge :status="record.status === 1 ? 'success' : 'default'" :text="record.status === 1 ? '正常' : '禁用'" />
            </template>

            <template v-else-if="column.key === 'last_login_at'">
              {{ record.last_login_at ? formatDateTime(record.last_login_at) : '从未登录' }}
            </template>

            <template v-else-if="column.key === 'created_at'">{{ formatDateTime(record.created_at) }}</template>

            <template v-else-if="column.key === 'action'">
              <a-space :size="2">
                <a-tooltip title="编辑">
                  <a-button size="small" type="text" @click="openEdit(record)">
                    <template #icon><EditOutlined /></template>
                  </a-button>
                </a-tooltip>
                <a-tooltip title="重置密码">
                  <a-button size="small" type="text" @click="openReset(record)">
                    <template #icon><KeyOutlined /></template>
                  </a-button>
                </a-tooltip>
                <a-popconfirm
                  title="删除该用户？其会话与知识库也会一并删除。"
                  ok-text="删除"
                  cancel-text="取消"
                  @confirm="handleDelete(record)"
                >
                  <a-button size="small" type="text" danger :disabled="record.id === userStore.user?.id">
                    <template #icon><DeleteOutlined /></template>
                  </a-button>
                </a-popconfirm>
              </a-space>
            </template>
          </template>
        </a-table>
      </a-card>
    </div>

    <!-- 新建 / 编辑 -->
    <a-modal
      v-model:open="formOpen"
      :title="editing ? '编辑用户' : '新建用户'"
      :confirm-loading="saving"
      ok-text="保存"
      cancel-text="取消"
      @ok="submit"
    >
      <a-form :model="form" layout="vertical">
        <a-form-item label="用户名" required>
          <a-input v-model:value="form.username" :disabled="Boolean(editing)" placeholder="3-32 位" />
        </a-form-item>
        <a-form-item v-if="!editing" label="密码" required>
          <a-input-password v-model:value="form.password" placeholder="至少 6 位" autocomplete="new-password" />
        </a-form-item>
        <a-form-item label="昵称">
          <a-input v-model:value="form.nickname" placeholder="可选" />
        </a-form-item>
        <a-form-item label="邮箱">
          <a-input v-model:value="form.email" placeholder="可选" />
        </a-form-item>
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="角色">
              <a-select
                v-model:value="form.role"
                :options="[
                  { value: 'user', label: '普通用户' },
                  { value: 'admin', label: '管理员' },
                ]"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="状态">
              <a-select
                v-model:value="form.status"
                :options="[
                  { value: 1, label: '正常' },
                  { value: 0, label: '禁用' },
                ]"
              />
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
    </a-modal>

    <!-- 重置密码 -->
    <a-modal v-model:open="resetOpen" title="重置密码" :confirm-loading="saving" ok-text="重置" @ok="submitReset">
      <p class="reset-hint">为用户「{{ resetTarget?.username }}」设置新密码：</p>
      <a-input-password v-model:value="newPassword" placeholder="至少 6 位" autocomplete="new-password" />
    </a-modal>
  </AdminLayout>
</template>

<script setup lang="ts">
/** 用户管理：列表 / 新建 / 编辑 / 重置密码 / 删除 */
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import type { TableColumnsType, TablePaginationConfig } from 'ant-design-vue'
import {
  DeleteOutlined,
  EditOutlined,
  KeyOutlined,
  ReloadOutlined,
  SearchOutlined,
  UserAddOutlined,
} from '@ant-design/icons-vue'

import LoadingView from '@/components/common/LoadingView.vue'
import AdminLayout from '@/layouts/AdminLayout.vue'
import { userApi, type UserPayload } from '@/api/user'
import { useUserStore } from '@/stores/user'
import type { UserInfo } from '@/types'
import { formatDateTime } from '@/utils/format'

const userStore = useUserStore()

const users = ref<UserInfo[]>([])
const loading = ref(false)
const saving = ref(false)
const formOpen = ref(false)
const resetOpen = ref(false)
const editing = ref<UserInfo | null>(null)
const resetTarget = ref<UserInfo | null>(null)
const newPassword = ref('')
const total = ref(0)
const filters = reactive<{ keyword?: string; role?: string }>({ keyword: undefined, role: undefined })
const page = reactive({ current: 1, pageSize: 10 })

const form = reactive<UserPayload>({
  username: '',
  password: '',
  nickname: '',
  email: '',
  role: 'user',
  status: 1,
})

const columns: TableColumnsType = [
  { title: '用户', key: 'username', width: 200 },
  { title: '邮箱', key: 'email', ellipsis: true },
  { title: '角色', key: 'role', width: 110 },
  { title: '状态', key: 'status', width: 100 },
  { title: '最后登录', key: 'last_login_at', width: 170 },
  { title: '创建时间', key: 'created_at', width: 170 },
  { title: '操作', key: 'action', width: 140, fixed: 'right' },
]

const paginationConfig = computed<TablePaginationConfig>(() => ({
  current: page.current,
  pageSize: page.pageSize,
  total: total.value,
  showSizeChanger: true,
  showTotal: (value: number) => `共 ${value} 条`,
}))

async function load() {
  loading.value = true
  try {
    const data = await userApi.list({
      page: page.current,
      page_size: page.pageSize,
      keyword: filters.keyword,
      role: filters.role,
    })
    users.value = data.items
    total.value = data.meta.total
  } finally {
    loading.value = false
  }
}

function handleTableChange(pagination: TablePaginationConfig) {
  page.current = pagination.current || 1
  page.pageSize = pagination.pageSize || 10
  load()
}

function openCreate() {
  editing.value = null
  Object.assign(form, { username: '', password: '', nickname: '', email: '', role: 'user', status: 1 })
  formOpen.value = true
}

function openEdit(record: UserInfo) {
  editing.value = record
  Object.assign(form, {
    username: record.username,
    password: '',
    nickname: record.nickname || '',
    email: record.email || '',
    role: record.role,
    status: record.status,
  })
  formOpen.value = true
}

async function submit() {
  if (!editing.value && (!form.username?.trim() || !form.password)) {
    message.warning('请填写用户名与密码')
    return
  }
  saving.value = true
  try {
    if (editing.value) {
      const payload: UserPayload = { ...form }
      delete payload.username
      delete payload.password
      await userApi.update(editing.value.id, payload)
      message.success('用户已更新')
    } else {
      await userApi.create(form)
      message.success('用户已创建')
    }
    formOpen.value = false
    await load()
  } finally {
    saving.value = false
  }
}

function openReset(record: UserInfo) {
  resetTarget.value = record
  newPassword.value = ''
  resetOpen.value = true
}

async function submitReset() {
  if (!resetTarget.value || newPassword.value.length < 6) {
    message.warning('密码至少 6 位')
    return
  }
  saving.value = true
  try {
    await userApi.resetPassword(resetTarget.value.id, newPassword.value)
    message.success('密码已重置')
    resetOpen.value = false
  } finally {
    saving.value = false
  }
}

async function handleDelete(record: UserInfo) {
  await userApi.remove(record.id)
  message.success('用户已删除')
  await load()
}

onMounted(load)
</script>

<style scoped>
.user-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.user-cell__info {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
  min-width: 0;
}

.user-cell__info small {
  font-size: 11px;
  color: var(--text-secondary);
}

.reset-hint {
  font-size: 13px;
  color: var(--text-secondary);
}
</style>
