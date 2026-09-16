/** 知识库 / 文档接口 */
import { request } from './request'
import type {
  DocumentChunkItem,
  DocumentItem,
  EmbeddingProviderInfo,
  KnowledgeBase,
  KnowledgeBasePayload,
  PageData,
  PageQuery,
  RetrievalTestResult,
} from '@/types'

export interface KnowledgeQuery extends PageQuery {
  keyword?: string
}

export interface DocumentQuery extends PageQuery {
  status?: string
  keyword?: string
}

export const knowledgeApi = {
  list(params: KnowledgeQuery = {}) {
    return request.get<PageData<KnowledgeBase>>('/knowledge-bases', { params: { page_size: 50, ...params } })
  },
  get(id: number) {
    return request.get<KnowledgeBase & { documents: DocumentItem[] }>(`/knowledge-bases/${id}`)
  },
  create(payload: KnowledgeBasePayload) {
    return request.post<KnowledgeBase>('/knowledge-bases', payload)
  },
  update(id: number, payload: Partial<KnowledgeBasePayload>) {
    return request.put<KnowledgeBase>(`/knowledge-bases/${id}`, payload)
  },
  remove(id: number) {
    return request.delete<{ message: string }>(`/knowledge-bases/${id}`)
  },
  retrievalTest(id: number, payload: { query: string; top_k?: number }) {
    return request.post<RetrievalTestResult>(`/knowledge-bases/${id}/retrieval-test`, payload)
  },
  embeddingCheck(id: number) {
    return request.get<{ provider: string; model: string; dimension: number }>(
      `/knowledge-bases/${id}/embedding-check`,
    )
  },
}

export const documentApi = {
  listByKb(kbId: number, params: DocumentQuery = {}) {
    return request.get<PageData<DocumentItem>>(`/knowledge-bases/${kbId}/documents`, {
      params: { page_size: 100, ...params },
    })
  },
  listAll(params: DocumentQuery = {}) {
    return request.get<PageData<DocumentItem>>('/documents', { params })
  },
  get(id: number) {
    return request.get<DocumentItem & { preview_chunks: DocumentChunkItem[] }>(`/documents/${id}`)
  },
  chunks(id: number, params: PageQuery = {}) {
    return request.get<PageData<DocumentChunkItem>>(`/documents/${id}/chunks`, { params })
  },
  upload(kbId: number, file: File, onProgress?: (percent: number) => void) {
    const form = new FormData()
    form.append('file', file)
    return request.upload<DocumentItem>(`/knowledge-bases/${kbId}/documents`, form, {
      onUploadProgress: (event) => {
        if (onProgress && event.total) {
          onProgress(Math.round((event.loaded / event.total) * 100))
        }
      },
    })
  },
  remove(id: number) {
    return request.delete<{ message: string }>(`/documents/${id}`)
  },
  reindex(id: number) {
    return request.post<DocumentItem>(`/documents/${id}/reindex`)
  },
  supportedTypes() {
    return request.get<string[]>('/documents/meta/supported-types')
  },
  limits() {
    return request.get<{ max_upload_size_mb: number; allowed_extensions: string[] }>('/documents/meta/limits')
  },
}

export const embeddingApi = {
  options() {
    return request.get<EmbeddingProviderInfo[]>('/models/embedding-options')
  },
}
