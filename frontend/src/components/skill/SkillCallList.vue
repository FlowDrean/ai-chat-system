<template>
  <div class="skill-call">
    <div class="skill-call__head" @click="expanded = !expanded">
      <ThunderboltOutlined class="skill-call__icon" />
      <span class="skill-call__title">
        已调用{{ hasMcp ? '技能 / MCP 工具' : '技能' }}（{{ calls.length }}）
      </span>
      <DownOutlined class="skill-call__arrow" :class="{ 'is-open': expanded }" />
    </div>
    <div v-if="expanded" class="skill-call__list">
      <div v-for="(call, index) in calls" :key="`${call.tool_name}-${index}`" class="skill-call__item">
        <div class="skill-call__item-head">
          <span class="skill-call__index">{{ index + 1 }}</span>
          <span class="skill-call__name">{{ call.name || call.tool_name }}</span>
          <a-tag v-if="call.source === 'mcp'" class="tag-mono is-strong skill-call__tag">MCP</a-tag>
          <a-tag v-if="call.status === 'error'" class="tag-mono is-error skill-call__tag">失败</a-tag>
          <span v-else-if="call.latency_ms" class="skill-call__latency">{{ call.latency_ms }}ms</span>
        </div>
        <div v-if="call.arguments && Object.keys(call.arguments).length" class="skill-call__row">
          <span class="skill-call__label">入参</span>
          <code class="skill-call__code">{{ JSON.stringify(call.arguments) }}</code>
        </div>
        <div class="skill-call__row">
          <span class="skill-call__label">结果</span>
          <pre class="skill-call__output">{{ call.output }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/** 助手消息下方的技能调用记录（默认折叠，点击展开看入参与结果） */
import { computed, ref } from 'vue'
import { DownOutlined, ThunderboltOutlined } from '@ant-design/icons-vue'

import type { SkillCall } from '@/types'

const props = defineProps<{ calls: SkillCall[] }>()

const hasMcp = computed(() => props.calls.some((item) => item.source === 'mcp'))

const expanded = ref(false)
</script>

<style scoped>
.skill-call {
  margin-top: 12px;
  padding: 8px 12px;
  background: var(--bg-sunken);
  border: 1px solid var(--border-color);
  border-radius: var(--radius);
}

.skill-call__head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
}

.skill-call__icon {
  color: var(--text-secondary);
}

.skill-call__arrow {
  margin-left: auto;
  font-size: 11px;
  transition: transform var(--transition);
}

.skill-call__arrow.is-open {
  transform: rotate(180deg);
}

.skill-call__list {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.skill-call__item {
  padding: 8px 10px;
  background: var(--bg-card);
  border: 1px solid var(--border-color);
  border-radius: 8px;
}

.skill-call__item-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
}

.skill-call__index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--bg-sunken);
  color: var(--text-secondary);
  font-size: 11px;
}

.skill-call__tag {
  font-size: 11px;
  margin-inline-end: 0;
}

.skill-call__latency {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-tertiary);
}

.skill-call__row {
  display: flex;
  gap: 8px;
  margin-top: 6px;
  font-size: 12px;
}

.skill-call__label {
  flex-shrink: 0;
  width: 28px;
  color: var(--text-tertiary);
}

.skill-call__code {
  font-size: 12px;
  word-break: break-all;
  color: var(--text-secondary);
}

.skill-call__output {
  margin: 0;
  flex: 1;
  max-height: 200px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
