<template>
  <a-drawer
    :open="open"
    title="模型参数"
    placement="right"
    :width="360"
    @close="emit('update:open', false)"
  >
    <a-form layout="vertical">
      <a-form-item>
        <template #label>
          <div class="row-between">
            <span>Temperature</span>
            <span class="value">{{ params.temperature?.toFixed(1) }}</span>
          </div>
        </template>
        <a-slider v-model:value="temperature" :min="0" :max="2" :step="0.1" :tip-formatter="null" />
        <p class="hint">值越高回答越发散，值越低越稳定。推荐 0.3 ~ 0.8。</p>
      </a-form-item>

      <a-form-item>
        <template #label>
          <div class="row-between">
            <span>Top P</span>
            <span class="value">{{ params.top_p?.toFixed(2) }}</span>
          </div>
        </template>
        <a-slider v-model:value="topP" :min="0" :max="1" :step="0.05" :tip-formatter="null" />
      </a-form-item>

      <a-form-item label="Max Tokens">
        <a-input-number v-model:value="maxTokens" :min="1" :max="131072" :step="256" style="width: 100%" />
        <p class="hint">单次回答的最大输出长度。</p>
      </a-form-item>

      <a-form-item>
        <template #label>
          <div class="row-between">
            <span>Frequency Penalty</span>
            <span class="value">{{ params.frequency_penalty?.toFixed(1) }}</span>
          </div>
        </template>
        <a-slider v-model:value="frequencyPenalty" :min="-2" :max="2" :step="0.1" :tip-formatter="null" />
      </a-form-item>

      <a-form-item>
        <template #label>
          <div class="row-between">
            <span>Presence Penalty</span>
            <span class="value">{{ params.presence_penalty?.toFixed(1) }}</span>
          </div>
        </template>
        <a-slider v-model:value="presencePenalty" :min="-2" :max="2" :step="0.1" :tip-formatter="null" />
      </a-form-item>

      <a-form-item>
        <div class="row-between">
          <span>流式输出（Streaming）</span>
          <a-switch v-model:checked="streaming" />
        </div>
      </a-form-item>

      <a-form-item>
        <div class="row-between">
          <span>自动使用知识库（RAG）</span>
          <a-switch v-model:checked="autoRag" />
        </div>
      </a-form-item>

      <a-form-item>
        <div class="row-between">
          <span>展示 Token / 耗时</span>
          <a-switch v-model:checked="showUsage" />
        </div>
      </a-form-item>
    </a-form>

    <template #footer>
      <div class="drawer-footer">
        <a-button @click="reset">恢复默认</a-button>
        <a-button type="primary" @click="emit('update:open', false)">完成</a-button>
      </div>
    </template>
  </a-drawer>
</template>

<script setup lang="ts">
/** 模型参数面板：只影响当前会话（见开发文档 §6） */
import { computed } from 'vue'

import { useSettingsStore } from '@/stores/settings'

defineProps<{ open: boolean }>()
const emit = defineEmits<{ (event: 'update:open', value: boolean): void }>()

const settings = useSettingsStore()
const params = computed(() => settings.params)

function bind(key: 'temperature' | 'top_p' | 'max_tokens' | 'frequency_penalty' | 'presence_penalty') {
  return computed<number>({
    get: () => Number(params.value[key] ?? 0),
    set: (value) => {
      settings.params = { ...settings.params, [key]: value }
    },
  })
}

const temperature = bind('temperature')
const topP = bind('top_p')
const maxTokens = bind('max_tokens')
const frequencyPenalty = bind('frequency_penalty')
const presencePenalty = bind('presence_penalty')

const streaming = computed({
  get: () => settings.params.streaming !== false,
  set: (value: boolean) => (settings.params = { ...settings.params, streaming: value }),
})

const autoRag = computed({
  get: () => settings.autoRag,
  set: (value: boolean) => (settings.autoRag = value),
})

const showUsage = computed({
  get: () => settings.showTokenUsage,
  set: (value: boolean) => (settings.showTokenUsage = value),
})

function reset() {
  settings.resetParams()
}
</script>

<style scoped>
.row-between {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
}

.value {
  font-size: 12px;
  color: var(--brand);
  font-weight: 600;
}

.hint {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
