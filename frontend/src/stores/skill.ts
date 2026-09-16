/** 技能（Skills）状态：聊天可用技能 + 管理端 CRUD */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { skillApi } from '@/api/skill'
import type { SkillItem, SkillOption, SkillPayload, SkillSpec, SkillTestResult } from '@/types'

export const useSkillStore = defineStore('skill', () => {
  /** 聊天页可选技能（已启用 + 完成配置 + 允许用户使用） */
  const available = ref<SkillOption[]>([])
  /** 管理端完整列表 */
  const skills = ref<SkillItem[]>([])
  const specs = ref<SkillSpec[]>([])
  const loading = ref(false)
  const loaded = ref(false)
  const specsLoaded = ref(false)

  const configuredSkills = computed(() => available.value.filter((item) => item.configured))
  const enabledCount = computed(() => skills.value.filter((item) => item.enabled).length)

  async function fetchAvailable(force = false) {
    if (loaded.value && !force) return available.value
    available.value = await skillApi.available()
    loaded.value = true
    return available.value
  }

  async function fetchSkills(force = false) {
    if (loading.value) return skills.value
    if (loaded.value && !force && skills.value.length) return skills.value
    loading.value = true
    try {
      const data = await skillApi.list({ page_size: 200 })
      skills.value = data.items
      return skills.value
    } finally {
      loading.value = false
    }
  }

  async function fetchSpecs(force = false) {
    if (specsLoaded.value && !force) return specs.value
    specs.value = await skillApi.specs()
    specsLoaded.value = true
    return specs.value
  }

  function specOf(type?: string | null): SkillSpec | undefined {
    if (!type) return undefined
    return specs.value.find((item) => item.type === type)
  }

  async function createSkill(payload: SkillPayload) {
    const created = await skillApi.create(payload)
    await Promise.all([fetchSkills(true), fetchAvailable(true)])
    return created
  }

  async function updateSkill(id: number, payload: Partial<SkillPayload>) {
    const updated = await skillApi.update(id, payload)
    await Promise.all([fetchSkills(true), fetchAvailable(true)])
    return updated
  }

  async function removeSkill(id: number) {
    await skillApi.remove(id)
    await Promise.all([fetchSkills(true), fetchAvailable(true)])
  }

  async function toggleSkill(id: number, enabled: boolean) {
    await skillApi.toggle(id, enabled)
    await Promise.all([fetchSkills(true), fetchAvailable(true)])
  }

  async function testSkill(
    id: number,
    args: Record<string, unknown> = {},
    config?: Record<string, unknown>,
  ): Promise<SkillTestResult> {
    return skillApi.test(id, args, config)
  }

  async function testDraft(
    type: string,
    args: Record<string, unknown> = {},
    config?: Record<string, unknown>,
  ): Promise<SkillTestResult> {
    return skillApi.testDraft(type, args, config)
  }

  return {
    available,
    skills,
    specs,
    loading,
    loaded,
    specsLoaded,
    configuredSkills,
    enabledCount,
    fetchAvailable,
    fetchSkills,
    fetchSpecs,
    specOf,
    createSkill,
    updateSkill,
    removeSkill,
    toggleSkill,
    testSkill,
    testDraft,
  }
})
