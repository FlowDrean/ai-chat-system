/** Prompt 管理接口 */
import { request } from './request'
import type { PageData, PageQuery, PromptItem, PromptPayload } from '@/types'

export interface PromptQuery extends PageQuery {
  keyword?: string
  scene?: string
  enabled?: boolean
}

export const promptApi = {
  list(params: PromptQuery = {}) {
    return request.get<PageData<PromptItem>>('/prompts', { params: { page_size: 100, ...params } })
  },
  get(id: number) {
    return request.get<PromptItem>(`/prompts/${id}`)
  },
  create(payload: PromptPayload) {
    return request.post<PromptItem>('/prompts', payload)
  },
  update(id: number, payload: Partial<PromptPayload>) {
    return request.put<PromptItem>(`/prompts/${id}`, payload)
  },
  remove(id: number) {
    return request.delete<{ message: string }>(`/prompts/${id}`)
  },
  render(id: number, variables: Record<string, string>) {
    return request.post<{ id: number; name: string; content: string; variables: string[]; missing: string[] }>(
      `/prompts/${id}/render`,
      { variables },
    )
  },
  duplicate(id: number) {
    return request.post<PromptItem>(`/prompts/${id}/duplicate`)
  },
}
