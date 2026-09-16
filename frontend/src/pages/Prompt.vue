<template>
  <AdminLayout>
    <div class="page-container">
      <div class="page-header">
        <div>
          <h1 class="page-title">Prompt 管理</h1>
          <p class="page-subtitle">
            沉淀 System Prompt 模板，支持变量 <code v-pre>{{question}}</code>、
            <code v-pre>{{context}}</code>、<code v-pre>{{user_name}}</code>，可在聊天时直接应用。
          </p>
        </div>
        <a-space>
          <a-input
            v-model:value="filters.keyword"
            placeholder="搜索 Prompt"
            allow-clear
            style="width: 200px"
            @press-enter="load"
          >
            <template #prefix><SearchOutlined /></template>
          </a-input>
          <a-select
            v-model:value="filters.scene"
            :options="sceneOptions"
            placeholder="全部场景"
            allow-clear
            style="width: 150px"
            @change="load"
          />
          <a-button @click="load">
            <template #icon><ReloadOutlined /></template>
          </a-button>
          <a-button type="primary" @click="openCreate">
            <template #icon><PlusOutlined /></template>
            新建 Prompt
          </a-button>
        </a-space>
      </div>

      <LoadingView v-if="loading && !prompts.length" text="加载 Prompt 中…" />

      <EmptyState
        v-else-if="!prompts.length"
        :icon="BulbOutlined"
        title="还没有 Prompt"
        description="创建一个 System Prompt，让 AI 按照你的要求回答。"
      >
        <a-button type="primary" @click="openCreate">新建 Prompt</a-button>
      </EmptyState>

      <div v-else class="prompt-page__grid">
        <div v-for="item in prompts" :key="item.id" class="prompt-card">
          <div class="prompt-card__head">
            <div class="prompt-card__title">
              <span class="text-ellipsis">{{ item.name }}</span>
              <a-tag v-if="item.is_builtin" class="tag-mono">内置</a-tag>
              <a-tag class="tag-mono" :class="{ 'is-muted': !item.enabled }"><span class="status-dot" :class="item.enabled ? 'is-ok' : ''" />{{ item.enabled ? '启用' : '停用' }}</a-tag>
            </div>
            <a-dropdown :trigger="['click']" placement="bottomRight">
              <button type="button" class="prompt-card__more" @click.stop><MoreOutlined /></button>
              <template #overlay>
                <a-menu @click="(info: MenuInfo) => handleAction(String(info.key), item)">
                  <a-menu-item key="view"><EyeOutlined /> 查看 / 编辑</a-menu-item>
                  <a-menu-item key="apply"><MessageOutlined /> 去聊天中使用</a-menu-item>
                  <a-menu-item key="duplicate"><CopyOutlined /> 复制</a-menu-item>
                  <a-menu-divider />
                  <a-menu-item key="delete" :disabled="item.is_builtin" danger>
                    <DeleteOutlined /> 删除
                  </a-menu-item>
                </a-menu>
              </template>
            </a-dropdown>
          </div>

          <p class="prompt-card__desc">{{ item.description || '暂无描述' }}</p>

          <pre class="prompt-card__content">{{ truncate(item.content, 200) }}</pre>

          <div class="prompt-card__footer">
            <a-tag v-for="tag in item.tags || []" :key="tag" class="prompt-card__tag">{{ tag }}</a-tag>
            <span v-for="v in item.variables || []" :key="v" class="prompt-card__var">{{ wrapVar(v) }}</span>
            <span class="prompt-card__time">{{ formatRelative(item.updated_at) }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 编辑抽屉 -->
    <a-drawer
      v-model:open="editorOpen"
      :title="editing ? '编辑 Prompt' : '新建 Prompt'"
      placement="right"
      :width="620"
    >
      <a-form :model="form" layout="vertical">
        <a-form-item label="名称" required>
          <a-input v-model:value="form.name" placeholder="例如：专业程序员助手" :maxlength="60" />
        </a-form-item>
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="使用场景">
              <a-select v-model:value="form.scene" :options="sceneOptions" />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="状态">
              <a-switch v-model:checked="form.enabled" checked-children="启用" un-checked-children="停用" />
            </a-form-item>
          </a-col>
        </a-row>
        <a-form-item label="描述">
          <a-input v-model:value="form.description" placeholder="可选" :maxlength="200" />
        </a-form-item>
        <a-form-item label="Prompt 内容" required>
          <a-textarea
            v-model:value="form.content"
            :rows="12"
            :maxlength="20000"
            :placeholder="promptPlaceholder"
          />
          <p class="editor-hint">
            检测到变量：
            <a-tag v-for="v in detectedVariables" :key="v" class="editor-var">{{ v }}</a-tag>
            <span v-if="!detectedVariables.length" class="text-secondary">无</span>
          </p>
        </a-form-item>
        <a-form-item label="标签">
          <a-select
            v-model:value="form.tags"
            mode="tags"
            placeholder="输入后回车添加，最多 12 个"
            :max-tag-count="8"
          />
        </a-form-item>

        <a-alert
          v-if="editing?.is_builtin"
          type="warning"
          show-icon
          message="系统内置 Prompt 不可修改，保存前请先点击「复制」生成自己的副本。"
          class="editor-alert"
        />
      </a-form>

      <template #footer>
        <div class="editor-footer">
          <a-button @click="editorOpen = false">取消</a-button>
          <a-button type="primary" :loading="saving" :disabled="editing?.is_builtin" @click="submit">
            保存
          </a-button>
        </div>
      </template>
    </a-drawer>
  </AdminLayout>
</template>

<script setup lang="ts">
/** Prompt 管理：卡片列表 + 抽屉编辑 + 变量提取 */
import { computed, onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import {
  BulbOutlined,
  CopyOutlined,
  DeleteOutlined,
  EyeOutlined,
  MessageOutlined,
  MoreOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue'
import { useRouter } from 'vue-router'

import EmptyState from '@/components/common/EmptyState.vue'
import LoadingView from '@/components/common/LoadingView.vue'
import AdminLayout from '@/layouts/AdminLayout.vue'
import { promptApi } from '@/api/prompt'
import type { PromptItem, PromptPayload } from '@/types'
import { formatRelative } from '@/utils/format'
import type { MenuInfo } from 'ant-design-vue/es/menu/src/interface'

const router = useRouter()

const prompts = ref<PromptItem[]>([])
const loading = ref(false)
const saving = ref(false)
const editorOpen = ref(false)
const editing = ref<PromptItem | null>(null)
const filters = reactive<{ keyword?: string; scene?: string }>({ keyword: undefined, scene: undefined })

const form = reactive<PromptPayload>({
  name: '',
  content: '',
  description: '',
  variables: [],
  tags: [],
  scene: 'system',
  enabled: true,
})

const promptPlaceholder = '支持 {{question}} / {{context}} / {{user_name}} 变量'

const sceneOptions = [
  { value: 'system', label: 'System Prompt' },
  { value: 'rag', label: 'RAG 模板' },
  { value: 'chat', label: '对话模板' },
]

const detectedVariables = computed(() => {
  const result = new Set<string>()
  const regex = /\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}/g
  let match: RegExpExecArray | null
  while ((match = regex.exec(form.content))) result.add(match[1])
  return [...result]
})

function wrapVar(name: string) {
  return `{{${name}}}`
}

function truncate(text: string, length: number) {
  return text.length > length ? `${text.slice(0, length)}…` : text
}

async function load() {
  loading.value = true
  try {
    const data = await promptApi.list({ page_size: 100, keyword: filters.keyword, scene: filters.scene })
    prompts.value = data.items
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editing.value = null
  Object.assign(form, {
    name: '',
    content: '',
    description: '',
    variables: [],
    tags: [],
    scene: 'system',
    enabled: true,
  })
  editorOpen.value = true
}

async function openEdit(item: PromptItem) {
  editing.value = item
  Object.assign(form, {
    name: item.name,
    content: item.content,
    description: item.description || '',
    variables: item.variables || [],
    tags: item.tags || [],
    scene: item.scene,
    enabled: item.enabled,
  })
  editorOpen.value = true
}

async function submit() {
  if (!form.name.trim() || !form.content.trim()) {
    message.warning('请填写名称与 Prompt 内容')
    return
  }
  saving.value = true
  try {
    const payload = { ...form, variables: detectedVariables.value }
    if (editing.value) {
      await promptApi.update(editing.value.id, payload)
      message.success('Prompt 已更新')
    } else {
      await promptApi.create(payload)
      message.success('Prompt 已创建')
    }
    editorOpen.value = false
    await load()
  } finally {
    saving.value = false
  }
}

async function handleAction(key: string, item: PromptItem) {
  if (key === 'view') await openEdit(item)
  else if (key === 'apply') {
    localStorage.setItem('ai_chat_pending_prompt', String(item.id))
    await router.push('/chat')
  } else if (key === 'duplicate') {
    await promptApi.duplicate(item.id)
    message.success('已复制为我的 Prompt')
    await load()
  } else if (key === 'delete') {
    await promptApi.remove(item.id)
    message.success('Prompt 已删除')
    await load()
  }
}

onMounted(load)
</script>

<style scoped>
.prompt-page__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 14px;
}

.prompt-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
  transition: var(--transition);
}

.prompt-card:hover {
  border-color: var(--border-dark);
  box-shadow: var(--shadow-card);
}

.prompt-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.prompt-card__title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  min-width: 0;
}

.prompt-card__more {
  border: none;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  width: 26px;
  height: 26px;
  border-radius: 6px;
}

.prompt-card__more:hover {
  background: var(--bg-hover);
}

.prompt-card__desc {
  margin: 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.prompt-card__content {
  margin: 0;
  padding: 10px 12px;
  background: var(--bg-sunken);
  border-radius: var(--radius-sm);
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
  white-space: pre-wrap;
  max-height: 132px;
  overflow: hidden;
}

.prompt-card__footer {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.prompt-card__tag {
  font-size: 11px;
  margin-inline-end: 0;
}

.prompt-card__var {
  font-size: 11px;
  color: var(--brand);
  background: var(--brand-soft);
  padding: 1px 6px;
  border-radius: 4px;
  font-family: monospace;
}

.prompt-card__time {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-tertiary);
}

.editor-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.editor-var {
  font-family: monospace;
  margin-inline-end: 4px;
}

.editor-alert {
  margin-top: 4px;
}

.editor-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
