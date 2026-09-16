/** 模型状态：模型列表 / 供应商 / 默认模型 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { modelApi } from '@/api/model'
import type { ModelItem, ModelPayload, ModelTestResult, ProviderInfo } from '@/types'

export const useModelStore = defineStore('model', () => {
  const models = ref<ModelItem[]>([])
  const providers = ref<ProviderInfo[]>([])
  const loading = ref(false)
  const loaded = ref(false)

  const enabledModels = computed(() => models.value.filter((item) => item.enabled))
  const defaultModel = computed(() => models.value.find((item) => item.is_default) || enabledModels.value[0] || null)

  function providerLabel(provider?: string | null): string {
    if (!provider) return '-'
    return providers.value.find((item) => item.value === provider)?.label || provider
  }

  async function fetchModels(force = false) {
    if (loading.value) return models.value
    if (loaded.value && !force) return models.value
    loading.value = true
    try {
      const data = await modelApi.list({ page_size: 200 })
      models.value = data.items
      loaded.value = true
      return models.value
    } finally {
      loading.value = false
    }
  }

  async function fetchProviders() {
    if (providers.value.length) return providers.value
    providers.value = await modelApi.providers()
    return providers.value
  }

  async function createModel(payload: ModelPayload) {
    const created = await modelApi.create(payload)
    await fetchModels(true)
    return created
  }

  async function updateModel(id: number, payload: Partial<ModelPayload>) {
    const updated = await modelApi.update(id, payload)
    await fetchModels(true)
    return updated
  }

  async function removeModel(id: number) {
    await modelApi.remove(id)
    await fetchModels(true)
  }

  async function setDefault(id: number) {
    await modelApi.setDefault(id)
    await fetchModels(true)
  }

  async function toggleModel(id: number, enabled: boolean) {
    await modelApi.toggle(id, enabled)
    await fetchModels(true)
  }

  async function testModel(id: number): Promise<ModelTestResult> {
    const result = await modelApi.test(id)
    await fetchModels(true)
    return result
  }

  async function duplicateModel(id: number) {
    await modelApi.duplicate(id)
    await fetchModels(true)
  }

  return {
    models,
    providers,
    loading,
    loaded,
    enabledModels,
    defaultModel,
    providerLabel,
    fetchModels,
    fetchProviders,
    createModel,
    updateModel,
    removeModel,
    setDefault,
    toggleModel,
    testModel,
    duplicateModel,
  }
})
