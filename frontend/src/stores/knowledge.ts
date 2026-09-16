/** 知识库状态：知识库列表 / 文档列表 / 上传进度 / 状态轮询 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { documentApi, embeddingApi, knowledgeApi } from '@/api/knowledge'
import type { DocumentItem, EmbeddingProviderInfo, KnowledgeBase, KnowledgeBasePayload } from '@/types'

export const useKnowledgeStore = defineStore('knowledge', () => {
  const knowledgeBases = ref<KnowledgeBase[]>([])
  const documents = ref<Record<number, DocumentItem[]>>({})
  const embeddingProviders = ref<EmbeddingProviderInfo[]>([])
  const loading = ref(false)
  const loaded = ref(false)

  const totalChunks = computed(() => knowledgeBases.value.reduce((sum, kb) => sum + kb.chunk_count, 0))
  const totalDocuments = computed(() => knowledgeBases.value.reduce((sum, kb) => sum + kb.document_count, 0))

  async function fetchKnowledgeBases(force = false) {
    if (loading.value) return knowledgeBases.value
    if (loaded.value && !force) return knowledgeBases.value
    loading.value = true
    try {
      const data = await knowledgeApi.list({ page_size: 100 })
      knowledgeBases.value = data.items
      loaded.value = true
      return knowledgeBases.value
    } finally {
      loading.value = false
    }
  }

  async function fetchEmbeddingProviders() {
    if (embeddingProviders.value.length) return embeddingProviders.value
    embeddingProviders.value = await embeddingApi.options()
    return embeddingProviders.value
  }

  async function createKnowledgeBase(payload: KnowledgeBasePayload) {
    const created = await knowledgeApi.create(payload)
    await fetchKnowledgeBases(true)
    return created
  }

  async function updateKnowledgeBase(id: number, payload: Partial<KnowledgeBasePayload>) {
    const updated = await knowledgeApi.update(id, payload)
    await fetchKnowledgeBases(true)
    return updated
  }

  async function removeKnowledgeBase(id: number) {
    await knowledgeApi.remove(id)
    delete documents.value[id]
    await fetchKnowledgeBases(true)
  }

  async function fetchDocuments(kbId: number, silent = false) {
    const data = await documentApi.listByKb(kbId, { page_size: 100 })
    documents.value[kbId] = data.items
    if (!silent) {
      const kb = knowledgeBases.value.find((item) => item.id === kbId)
      if (kb) {
        kb.document_count = data.meta.total
      }
    }
    return data.items
  }

  async function uploadDocument(kbId: number, file: File, onProgress?: (percent: number) => void) {
    const document = await documentApi.upload(kbId, file, onProgress)
    await fetchDocuments(kbId, true)
    return document
  }

  async function removeDocument(kbId: number, documentId: number) {
    await documentApi.remove(documentId)
    await fetchDocuments(kbId, true)
    await fetchKnowledgeBases(true)
  }

  async function reindexDocument(kbId: number, documentId: number) {
    const document = await documentApi.reindex(documentId)
    await fetchDocuments(kbId, true)
    return document
  }

  /** 轮询处理中（pending/parsing/splitting/embedding）的文档，直到全部结束 */
  function startPolling(kbId: number, intervalMs = 2500, onUpdate?: (items: DocumentItem[]) => void) {
    let stopped = false
    const timer = window.setInterval(async () => {
      if (stopped) return
      try {
        const items = await fetchDocuments(kbId, true)
        onUpdate?.(items)
        const processing = items.some((item) =>
          ['pending', 'parsing', 'splitting', 'embedding'].includes(item.status),
        )
        if (!processing) {
          stop()
          await fetchKnowledgeBases(true)
        }
      } catch {
        stop()
      }
    }, intervalMs)

    function stop() {
      stopped = true
      window.clearInterval(timer)
    }

    // 立即跑一次
    fetchDocuments(kbId, true).then((items) => onUpdate?.(items)).catch(() => undefined)

    return stop
  }

  return {
    knowledgeBases,
    documents,
    embeddingProviders,
    loading,
    loaded,
    totalChunks,
    totalDocuments,
    fetchKnowledgeBases,
    fetchEmbeddingProviders,
    createKnowledgeBase,
    updateKnowledgeBase,
    removeKnowledgeBase,
    fetchDocuments,
    uploadDocument,
    removeDocument,
    reindexDocument,
    startPolling,
  }
})
