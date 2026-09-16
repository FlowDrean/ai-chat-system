<template>
  <div class="skill-form">
    <!-- 基本信息 -->
    <a-form ref="formRef" :model="form" :rules="rules" layout="vertical">
      <a-row :gutter="16">
        <a-col :xs="24" :md="12">
          <a-form-item label="技能名称" name="name">
            <a-input v-model:value="form.name" :maxlength="32" placeholder="例如：订单查询接口" />
          </a-form-item>
        </a-col>
        <a-col :xs="24" :md="12">
          <a-form-item label="技能类型">
            <a-input :value="spec?.name || type" disabled />
          </a-form-item>
        </a-col>
        <a-col :span="24">
          <a-form-item label="用途说明（告诉模型什么时候该用它）" name="description">
            <a-textarea
              v-model:value="form.description"
              :rows="2"
              :maxlength="500"
              :placeholder="spec?.description"
            />
          </a-form-item>
        </a-col>
        <a-col :xs="12" :md="8">
          <a-form-item label="启用">
            <a-switch v-model:checked="form.enabled" />
          </a-form-item>
        </a-col>
        <a-col :xs="12" :md="8">
          <a-form-item label="允许用户选择">
            <a-switch v-model:checked="form.visible_to_users" />
          </a-form-item>
        </a-col>
        <a-col :xs="12" :md="8">
          <a-form-item label="排序">
            <a-input-number v-model:value="form.sort_order" :min="0" :max="999" style="width: 100%" />
          </a-form-item>
        </a-col>
      </a-row>

      <!-- 动态配置项 -->
      <a-divider orientation="left" class="skill-form__divider">技能配置</a-divider>
      <a-row :gutter="16">
        <a-col v-for="field in spec?.fields || []" :key="field.key" :xs="24" :md="field.type === 'json' ? 24 : 12">
          <a-form-item :label="field.label" :required="field.required">
            <template v-if="field.type === 'password'">
              <a-input-password
                v-model:value="configValues[field.key]"
                :placeholder="passwordPlaceholder(field)"
                autocomplete="new-password"
              />
            </template>
            <template v-else-if="field.type === 'text' || field.type === 'json'">
              <a-textarea
                v-model:value="configValues[field.key]"
                :rows="field.type === 'json' ? 5 : 2"
                :placeholder="field.placeholder"
                class="skill-form__mono"
              />
            </template>
            <template v-else-if="field.type === 'boolean'">
              <a-switch v-model:checked="booleanValues[field.key]" />
            </template>
            <template v-else-if="field.type === 'number' || field.type === 'integer'">
              <a-input-number
                v-model:value="numberValues[field.key]"
                :precision="field.type === 'integer' ? 0 : undefined"
                style="width: 100%"
              />
            </template>
            <template v-else-if="field.type === 'select'">
              <a-select v-model:value="configValues[field.key]" :options="field.options || []" />
            </template>
            <template v-else>
              <a-input v-model:value="configValues[field.key]" :placeholder="field.placeholder" />
            </template>
            <p v-if="field.help" class="skill-form__help">{{ field.help }}</p>
          </a-form-item>
        </a-col>
      </a-row>

      <!-- 试运行 -->
      <a-divider orientation="left" class="skill-form__divider">试运行</a-divider>
      <p class="skill-form__help">
        按模型调用时的方式填入参数即可测试；自带示例值可留空直接运行。
      </p>
      <a-row :gutter="16">
        <a-col v-for="arg in testArgs" :key="arg.name" :xs="24" :md="12">
          <a-form-item :label="`${arg.name}（${arg.type}）`">
            <a-input
              v-model:value="testValues[arg.name]"
              :placeholder="arg.description || arg.name"
            />
            <p v-if="arg.description" class="skill-form__help">{{ arg.description }}</p>
          </a-form-item>
        </a-col>
      </a-row>

      <a-space>
        <a-button :loading="testing" @click="runTest">
          <template #icon><PlayCircleOutlined /></template>
          试运行
        </a-button>
        <span class="text-secondary skill-form__help">使用「当前表单里的配置」执行，不需要先保存</span>
      </a-space>

      <a-alert
        v-if="testResult"
        class="skill-form__result"
        :type="testResult.success ? 'success' : 'error'"
        show-icon
        :message="testResult.success ? `执行成功（${testResult.latency_ms}ms）` : testResult.error || '执行失败'"
      >
        <template v-if="testResult.output" #description>
          <pre class="skill-form__output">{{ testResult.output }}</pre>
        </template>
      </a-alert>
    </a-form>
  </div>
</template>

<script setup lang="ts">
/**
 * 技能动态配置表单
 * 完全由后端返回的 `SkillSpec.fields` 驱动渲染，新增技能类型无需改前端。
 */
import { computed, reactive, ref, watch } from 'vue'
import type { FormInstance } from 'ant-design-vue'
import type { Rule } from 'ant-design-vue/es/form'
import { PlayCircleOutlined } from '@ant-design/icons-vue'

import { useSkillStore } from '@/stores/skill'
import type { SkillArg, SkillField, SkillItem, SkillSpec, SkillTestResult } from '@/types'

const props = defineProps<{
  type: string
  current?: SkillItem | null
}>()

const emit = defineEmits<{ (event: 'result', value: SkillTestResult): void }>()

const store = useSkillStore()
const formRef = ref<FormInstance>()
const testing = ref(false)
const testResult = ref<SkillTestResult | null>(null)

const form = reactive({
  name: '',
  description: '',
  enabled: true,
  visible_to_users: true,
  sort_order: 0,
})

/** 配置项：字符串类与布尔/数字分开绑定，避免类型抖动 */
const configValues = reactive<Record<string, string>>({})
const numberValues = reactive<Record<string, number | null>>({})
const booleanValues = reactive<Record<string, boolean>>({})
const testValues = reactive<Record<string, string>>({})

const spec = computed<SkillSpec | undefined>(() => store.specOf(props.type) || props.current?.spec || undefined)

const rules: Record<string, Rule[]> = {
  name: [{ required: true, message: '请输入技能名称', trigger: 'blur' }],
}

/** 试运行参数：固定入参 or 自定义技能的动态入参 */
const testArgs = computed<SkillArg[]>(() => {
  const current = spec.value
  if (!current) return []
  if (current.uses_dynamic_args) {
    try {
      const raw = JSON.parse(configValues.args_schema || '{}')
      return Object.entries(raw).map(([name, definition]) => {
        const def = definition as Record<string, unknown> | string
        return {
          name,
          type: (typeof def === 'string' ? 'string' : String(def.type || 'string')) as SkillArg['type'],
          description: typeof def === 'string' ? def : String(def.description || ''),
          required: true,
        }
      })
    } catch {
      return []
    }
  }
  return current.args
})

function passwordPlaceholder(field: SkillField) {
  const masked = props.current?.config?.[field.key]
  if (props.current?.config_masked_keys?.includes(field.key) && masked) {
    return `已配置：${masked}（留空表示不修改）`
  }
  return field.placeholder || '请输入'
}

function reset() {
  const current = props.current
  form.name = current?.name || ''
  form.description = current?.description || spec.value?.description || ''
  form.enabled = current?.enabled ?? true
  form.visible_to_users = current?.visible_to_users ?? true
  form.sort_order = current?.sort_order ?? 0
  testResult.value = null

  Object.keys(configValues).forEach((key) => delete configValues[key])
  Object.keys(numberValues).forEach((key) => delete numberValues[key])
  Object.keys(booleanValues).forEach((key) => delete booleanValues[key])
  Object.keys(testValues).forEach((key) => delete testValues[key])

  for (const field of spec.value?.fields || []) {
    const saved = current?.config?.[field.key]
    const value = saved !== undefined && saved !== null ? saved : field.default
    if (field.type === 'boolean') {
      booleanValues[field.key] = Boolean(value)
    } else if (field.type === 'number' || field.type === 'integer') {
      numberValues[field.key] = value === undefined || value === null || value === '' ? null : Number(value)
    } else if (field.type === 'password') {
      // 敏感项：留空表示不修改（后端会保留原值）
      configValues[field.key] = ''
    } else if (field.type === 'json') {
      configValues[field.key] = typeof value === 'string' ? value : JSON.stringify(value ?? {}, null, 2)
    } else {
      configValues[field.key] = value === undefined || value === null ? '' : String(value)
    }
  }
}

watch(() => [props.type, props.current?.id], reset, { immediate: true, deep: true })

/** 组装完整配置（含类型转换），供保存与试运行复用 */
function buildConfig(): Record<string, unknown> {
  const config: Record<string, unknown> = {}
  for (const field of spec.value?.fields || []) {
    if (field.type === 'boolean') {
      config[field.key] = booleanValues[field.key] ?? false
    } else if (field.type === 'number' || field.type === 'integer') {
      const value = numberValues[field.key]
      if (value !== null && value !== undefined) config[field.key] = value
    } else if (field.type === 'json') {
      const raw = configValues[field.key]
      if (raw) {
        try {
          config[field.key] = JSON.parse(raw)
        } catch {
          config[field.key] = raw
        }
      } else {
        config[field.key] = {}
      }
    } else {
      const value = configValues[field.key]
      // 密码类留空 => 不下发该字段（后端保留原值）
      if (value !== '' || field.required === false) config[field.key] = value
    }
  }
  return config
}

async function runTest() {
  testing.value = true
  testResult.value = null
  try {
    const args: Record<string, unknown> = {}
    for (const [key, value] of Object.entries(testValues)) {
      const arg = testArgs.value.find((item) => item.name === key)
      args[key] = arg && (arg.type === 'number' || arg.type === 'integer') && value !== '' ? Number(value) : value
    }
    const result = props.current?.id
      ? await store.testSkill(props.current.id, args, buildConfig())
      : await store.testDraft(props.type, args, buildConfig())
    testResult.value = result
    emit('result', result)
  } finally {
    testing.value = false
  }
}

async function validate(): Promise<boolean> {
  try {
    await formRef.value?.validate()
    return true
  } catch {
    return false
  }
}

defineExpose({
  buildConfig,
  validate,
  getForm: () => ({ ...form }),
})
</script>

<style scoped>
.skill-form__divider {
  margin: 8px 0 16px;
  font-size: 13px;
  color: var(--text-secondary);
}

.skill-form__help {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.skill-form__mono :deep(textarea) {
  font-family: 'JetBrains Mono', Consolas, monospace;
  font-size: 12px;
}

.skill-form__result {
  margin-top: 12px;
}

.skill-form__output {
  margin: 0;
  max-height: 220px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
