/** 模型管理接口 */
import { request } from './request'
import type { ModelItem, ModelPayload, ModelTestResult, PageData, ProviderInfo } from '@/types'

export interface ModelQuery {
  keyword?: string
  provider?: string
  enabled?: boolean
  page?: number
  page_size?: number
}

export const modelApi = {
  list(params: ModelQuery = {}) {
    return request.get<PageData<ModelItem>>('/models', { params: { page_size: 100, ...params } })
  },
  providers() {
    return request.get<ProviderInfo[]>('/models/providers')
  },
  get(id: number) {
    return request.get<ModelItem>(`/models/${id}`)
  },
  create(payload: ModelPayload) {
    return request.post<ModelItem>('/models', payload)
  },
  update(id: number, payload: Partial<ModelPayload>) {
    return request.put<ModelItem>(`/models/${id}`, payload)
  },
  remove(id: number) {
    return request.delete<{ message: string }>(`/models/${id}`)
  },
  test(id: number) {
    return request.post<ModelTestResult>(`/models/${id}/test`, undefined, { timeout: 120_000 })
  },
  setDefault(id: number) {
    return request.post<ModelItem>(`/models/${id}/default`)
  },
  toggle(id: number, enabled: boolean) {
    return request.patch<ModelItem>(`/models/${id}/enabled`, undefined, { params: { enabled } })
  },
  duplicate(id: number) {
    return request.post<ModelItem>(`/models/${id}/duplicate`)
  },
}
