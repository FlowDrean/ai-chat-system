<template>
  <a-popover v-model:open="open" trigger="click" placement="topRight" :overlay-style="{ width: '360px' }">
    <template #content>
      <div class="skill-selector__panel">
        <div class="skill-selector__head">
          <div>
            <strong>技能</strong>
            <p class="skill-selector__desc">勾选后，模型会在需要时自动调用这些技能</p>
          </div>
          <a-button v-if="selected.length" type="link" size="small" @click="clearAll">清空</a-button>
        </div>

        <a-spin :spinning="store.loading">
          <EmptyState
            v-if="!store.available.length"
            :icon="ApiOutlined"
            title="暂无可用的技能"
            description="请先在「技能管理」中启用并完成配置。"
          >
            <a-button size="small" type="primary" @click="goManage">去配置</a-button>
          </EmptyState>

          <div v-else class="skill-selector__list">
            <label
              v-for="item in store.available"
              :key="item.id"
              class="skill-selector__item"
              :class="{ 'is-disabled': !item.configured }"
            >
              <a-checkbox
                :checked="selected.includes(item.id)"
                :disabled="!item.configured"
                @change="(event: CheckboxChangeEvent) => toggle(item, event)"
              />
              <div class="skill-selector__info">
                <div class="skill-selector__name">
                  <span>{{ item.name }}</span>
                  <a-tag v-if="!item.configured" class="tag-mono is-muted skill-selector__tag">未配置</a-tag>
                </div>
                <p class="skill-selector__text">{{ item.description || '暂无说明' }}</p>
              </div>
            </label>
          </div>
        </a-spin>

        <div class="skill-selector__footer">
          <span class="text-secondary">已选 {{ selected.length }} 个</span>
          <a-button type="link" size="small" @click="goManage">管理技能</a-button>
        </div>
      </div>
    </template>

    <a-tooltip :title="selected.length ? `已启用 ${selected.length} 个技能` : '选择技能'">
      <button type="button" class="tool-btn" :class="{ active: selected.length > 0 }">
        <ThunderboltOutlined />
        <span v-if="selected.length" class="tool-btn__badge">{{ selected.length }}</span>
      </button>
    </a-tooltip>
  </a-popover>
</template>

<script setup lang="ts">
/**
 * 技能选择器（聊天输入框工具栏）
 * 选中的技能会随请求发送（skill_ids），并保存到会话上，下次进入该会话自动恢复。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ApiOutlined, ThunderboltOutlined } from '@ant-design/icons-vue'
import type { CheckboxChangeEvent } from 'ant-design-vue/es/checkbox/interface'

import EmptyState from '@/components/common/EmptyState.vue'
import { useSkillStore } from '@/stores/skill'
import type { SkillOption } from '@/types'

const props = defineProps<{ modelValue?: number[] | null }>()
const emit = defineEmits<{ (event: 'update:modelValue', value: number[]): void }>()

const router = useRouter()
const store = useSkillStore()
const open = ref(false)

const selected = computed(() => props.modelValue || [])

onMounted(() => {
  store.fetchAvailable().catch(() => undefined)
})

function toggle(item: SkillOption, event: CheckboxChangeEvent) {
  const next = new Set(selected.value)
  if (event.target.checked) next.add(item.id)
  else next.delete(item.id)
  emit('update:modelValue', [...next])
}

function clearAll() {
  emit('update:modelValue', [])
}

function goManage() {
  open.value = false
  router.push('/admin/skills')
}
</script>

<style scoped>
.skill-selector__panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.skill-selector__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
}

.skill-selector__desc {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.skill-selector__list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 320px;
  overflow-y: auto;
}

.skill-selector__item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px;
  border-radius: 8px;
  cursor: pointer;
  transition: background var(--transition);
}

.skill-selector__item:hover {
  background: var(--bg-hover);
}

.skill-selector__item.is-disabled {
  cursor: not-allowed;
  opacity: 0.75;
}

.skill-selector__info {
  min-width: 0;
}

.skill-selector__name {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 500;
}

.skill-selector__tag {
  font-size: 11px;
  margin-inline-end: 0;
}

.skill-selector__text {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.skill-selector__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 8px;
  border-top: 1px solid var(--border-color);
  font-size: 12px;
}

.tool-btn__badge {
  position: absolute;
  top: 1px;
  right: 2px;
  min-width: 14px;
  height: 14px;
  padding: 0 3px;
  border-radius: 7px;
  background: var(--brand);
  color: var(--brand-contrast);
  font-size: 10px;
  line-height: 14px;
  text-align: center;
}
</style>
