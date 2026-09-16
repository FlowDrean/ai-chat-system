<template>
  <AdminLayout>
    <div class="page-container">
      <div class="page-header">
        <div>
          <h1 class="page-title">技能管理</h1>
          <p class="page-subtitle">
            为 AI 配置可调用的能力（计算、时间、联网搜索、网页抓取、自定义 HTTP 接口）。
            启用并完成配置后，即可在聊天中勾选使用。
          </p>
        </div>
        <a-space>
          <a-input
            v-model:value="filters.keyword"
            placeholder="搜索技能"
            allow-clear
            style="width: 200px"
            @press-enter="load"
          >
            <template #prefix><SearchOutlined /></template>
          </a-input>
          <a-select
            v-model:value="filters.type"
            :options="typeOptions"
            placeholder="全部类型"
            allow-clear
            style="width: 180px"
            @change="load"
          />
          <a-button @click="load">
            <template #icon><ReloadOutlined /></template>
          </a-button>
          <a-button type="primary" @click="openCreate">
            <template #icon><PlusOutlined /></template>
            新建技能
          </a-button>
        </a-space>
      </div>

      <a-row :gutter="14" class="skill-page__stats">
        <a-col :xs="12" :md="6">
          <StatCard label="技能总数" :value="skills.length" :icon="ApiOutlined" />
        </a-col>
        <a-col :xs="12" :md="6">
          <StatCard label="已启用" :value="skills.filter((item) => item.enabled).length" :icon="ThunderboltOutlined" />
        </a-col>
        <a-col :xs="12" :md="6">
          <StatCard
            label="聊天可用"
            :value="skills.filter((item) => item.enabled && item.visible_to_users).length"
            :icon="MessageOutlined"
          />
        </a-col>
        <a-col :xs="12" :md="6">
          <StatCard
            label="累计调用"
            :value="skills.reduce((sum, item) => sum + (item.usage_count || 0), 0)"
            :icon="RiseOutlined"
          />
        </a-col>
      </a-row>

      <a-card :bordered="true" size="small">
        <LoadingView v-if="loading && !skills.length" text="加载技能中…" />

        <EmptyState
          v-else-if="!skills.length"
          :icon="ApiOutlined"
          title="还没有技能"
          description="创建技能后，AI 就能在对话中调用它们（如查询内部接口、抓取网页、联网搜索）。"
        >
          <a-button type="primary" @click="openCreate">新建技能</a-button>
        </EmptyState>

        <a-table v-else :data-source="skills" :columns="columns" row-key="id" :pagination="false" size="middle">
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'name'">
              <div class="skill-name">
                <span class="skill-name__icon"><ThunderboltOutlined /></span>
                <div class="skill-name__info">
                  <span class="text-ellipsis">{{ record.name }}</span>
                  <small class="mono text-secondary">{{ record.slug }}</small>
                </div>
                <a-tag v-if="record.is_builtin" class="tag-mono skill-name__tag">内置</a-tag>
              </div>
            </template>

            <template v-else-if="column.key === 'type'">
              <a-tag class="tag-mono">{{ record.type_label || record.type }}</a-tag>
            </template>

            <template v-else-if="column.key === 'description'">
              <span class="text-secondary skill-desc">{{ record.description || '-' }}</span>
            </template>

            <template v-else-if="column.key === 'config'">
              <a-tag v-if="isConfigured(record)" class="tag-mono"><span class="status-dot is-ok" />已配置</a-tag>
              <a-tag v-else class="tag-mono is-muted">待配置</a-tag>
            </template>

            <template v-else-if="column.key === 'enabled'">
              <a-switch
                :checked="record.enabled"
                size="small"
                @change="(checked: unknown) => handleToggle(record, Boolean(checked))"
              />
            </template>

            <template v-else-if="column.key === 'usage_count'">
              {{ record.usage_count || 0 }}
            </template>

            <template v-else-if="column.key === 'last_used_at'">
              {{ record.last_used_at ? formatDateTime(record.last_used_at) : '未使用' }}
            </template>

            <template v-else-if="column.key === 'action'">
              <a-space :size="2">
                <a-tooltip title="配置 / 试运行">
                  <a-button size="small" type="text" @click="openEdit(record)">
                    <template #icon><SettingOutlined /></template>
                  </a-button>
                </a-tooltip>
                <a-tooltip title="在聊天中使用">
                  <a-button size="small" type="text" :disabled="!record.enabled" @click="goChat">
                    <template #icon><MessageOutlined /></template>
                  </a-button>
                </a-tooltip>
                <a-popconfirm
                  :title="record.is_builtin ? '系统预置技能不可删除，可将其禁用' : '删除该技能？'"
                  ok-text="删除"
                  cancel-text="取消"
                  :disabled="record.is_builtin"
                  @confirm="handleDelete(record)"
                >
                  <a-button size="small" type="text" danger :disabled="record.is_builtin">
                    <template #icon><DeleteOutlined /></template>
                  </a-button>
                </a-popconfirm>
              </a-space>
            </template>
          </template>
        </a-table>
      </a-card>

      <!-- 使用说明 -->
      <a-card :bordered="true" size="small" title="怎么用？" class="skill-page__guide">
        <a-steps :current="1" size="small" :responsive="true">
          <a-step title="配置技能" description="新建技能并填写配置（API Key / 接口地址等）" />
          <a-step title="启用技能" description="打开「启用」与「允许用户选择」" />
          <a-step title="聊天中勾选" description="在输入框工具栏点⚡选择技能，模型会按需自动调用" />
        </a-steps>
        <a-alert
          type="info"
          show-icon
          class="skill-page__tip"
          message="技能调用由模型的 Function Calling 能力驱动"
          description="DeepSeek / OpenAI / 通义 等支持工具调用的模型可直接使用；若所选模型不支持，系统会自动降级为普通对话并给出提示。"
        />
      </a-card>
    </div>

    <!-- 新建 / 配置抽屉 -->
    <a-drawer
      v-model:open="editorOpen"
      :title="editing ? `配置技能：${editing.name}` : '新建技能'"
      placement="right"
      :width="720"
      destroy-on-close
    >
      <div v-if="!editing" class="skill-page__type-picker">
        <div class="skill-page__type-label">选择技能类型</div>
        <div class="skill-page__type-grid">
          <button
            v-for="item in specs"
            :key="item.type"
            type="button"
            class="skill-type"
            :class="{ active: formType === item.type }"
            @click="formType = item.type"
          >
            <strong>{{ item.name }}</strong>
            <span>{{ item.description }}</span>
          </button>
        </div>
      </div>

      <SkillConfigForm
        v-if="formType"
        ref="configFormRef"
        :type="formType"
        :current="editing"
        @result="handleTestResult"
      />

      <template #footer>
        <div class="skill-page__footer">
          <span v-if="lastTest" class="text-secondary skill-page__footer-tip">
            最近一次试运行：{{ lastTest.success ? '成功' : '失败' }}
          </span>
          <a-space>
            <a-button @click="editorOpen = false">取消</a-button>
            <a-button type="primary" :loading="saving" @click="submit">保存</a-button>
          </a-space>
        </div>
      </template>
    </a-drawer>
  </AdminLayout>
</template>

<script setup lang="ts">
/** 技能管理：列表 / 新建 / 配置 / 试运行 / 启停 / 删除 */
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import type { TableColumnsType } from 'ant-design-vue'
import {
  ApiOutlined,
  DeleteOutlined,
  MessageOutlined,
  PlusOutlined,
  ReloadOutlined,
  RiseOutlined,
  SearchOutlined,
  SettingOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons-vue'
import { useRouter } from 'vue-router'

import EmptyState from '@/components/common/EmptyState.vue'
import LoadingView from '@/components/common/LoadingView.vue'
import StatCard from '@/components/common/StatCard.vue'
import SkillConfigForm from '@/components/skill/SkillConfigForm.vue'
import AdminLayout from '@/layouts/AdminLayout.vue'
import { useSkillStore } from '@/stores/skill'
import type { SkillItem, SkillPayload, SkillTestResult } from '@/types'
import { formatDateTime } from '@/utils/format'

const router = useRouter()
const store = useSkillStore()

const loading = ref(false)
const saving = ref(false)
const editorOpen = ref(false)
const editing = ref<SkillItem | null>(null)
const formType = ref<string>('')
const lastTest = ref<SkillTestResult | null>(null)
const configFormRef = ref<InstanceType<typeof SkillConfigForm> | null>(null)
const filters = reactive<{ keyword?: string; type?: string }>({ keyword: undefined, type: undefined })

const skills = computed(() => store.skills)
const specs = computed(() => store.specs)

const typeOptions = computed(() => store.specs.map((item) => ({ value: item.type, label: item.name })))

const columns: TableColumnsType = [
  { title: '技能', key: 'name', width: 220 },
  { title: '类型', key: 'type', width: 150 },
  { title: '用途说明', key: 'description', ellipsis: true },
  { title: '配置', key: 'config', width: 100 },
  { title: '启用', key: 'enabled', width: 80 },
  { title: '调用次数', key: 'usage_count', width: 100 },
  { title: '最近调用', key: 'last_used_at', width: 160 },
  { title: '操作', key: 'action', width: 150, fixed: 'right' },
]

function isConfigured(record: SkillItem): boolean {
  const spec = store.specOf(record.type) || record.spec
  if (!spec) return true
  const config = record.config || {}
  for (const field of spec.fields) {
    if (field.required && !config[field.key]) return false
  }
  return true
}

async function load() {
  loading.value = true
  try {
    await store.fetchSkills(true)
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  lastTest.value = null
  formType.value = store.specs.find((item) => item.type === 'http_request')?.type || store.specs[0]?.type || ''
  editorOpen.value = true
}

function openEdit(record: SkillItem) {
  editing.value = record
  lastTest.value = null
  formType.value = record.type
  editorOpen.value = true
}

function handleTestResult(result: SkillTestResult) {
  lastTest.value = result
}

function goChat() {
  router.push('/chat')
}

async function submit() {
  const form = configFormRef.value
  if (!form) return
  const valid = await form.validate()
  if (!valid) return
  const basic = form.getForm()

  saving.value = true
  try {
    const payload: SkillPayload = {
      name: basic.name,
      type: formType.value,
      description: basic.description,
      enabled: basic.enabled,
      visible_to_users: basic.visible_to_users,
      sort_order: basic.sort_order,
      config: form.buildConfig(),
    }
    if (editing.value) {
      await store.updateSkill(editing.value.id, payload)
      message.success('技能已更新')
    } else {
      await store.createSkill(payload)
      message.success('技能已创建')
    }
    editorOpen.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function handleToggle(record: SkillItem, enabled: boolean) {
  await store.toggleSkill(record.id, enabled)
  message.success(enabled ? '技能已启用' : '技能已禁用')
}

async function handleDelete(record: SkillItem) {
  await store.removeSkill(record.id)
  message.success('技能已删除')
  await load()
}

onMounted(async () => {
  await Promise.all([store.fetchSpecs(), load()])
})
</script>

<style scoped>
.skill-page__stats {
  margin-bottom: 16px;
}

.skill-name {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.skill-name__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: var(--bg-sunken);
  border: 1px solid var(--border-color);
  color: var(--text-primary);
  flex-shrink: 0;
}

.skill-name__info {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
  min-width: 0;
}

.skill-name__info small {
  font-size: 11px;
}

.skill-name__tag {
  font-size: 11px;
  margin-inline-end: 0;
}

.skill-desc {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  font-size: 12px;
}

.skill-page__guide {
  margin: 16px 0 24px;
}

.skill-page__tip {
  margin-top: 16px;
}

.skill-page__type-picker {
  margin-bottom: 16px;
}

.skill-page__type-label {
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
}

.skill-page__type-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 10px;
}

.skill-type {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  text-align: left;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  cursor: pointer;
  transition: var(--transition);
}

.skill-type:hover,
.skill-type.active {
  border-color: var(--brand);
  background: var(--brand-soft);
}

.skill-type strong {
  font-size: 13px;
}

.skill-type span {
  font-size: 11px;
  color: var(--text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.skill-page__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.skill-page__footer-tip {
  font-size: 12px;
}
</style>
