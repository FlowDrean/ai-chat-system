/** 聊天 / 会话接口 */
import { request } from './request'
import type { ChatMessage, ChatRequestPayload, ChatResult, Conversation, PageData, PageQuery } from '@/types'

export interface ConversationQuery extends PageQuery {
  keyword?: string
  favorite?: boolean
  archived?: boolean
}

export const chatApi = {
  /** 非流式聊天 */
  chat(payload: ChatRequestPayload) {
    return request.post<ChatResult>('/chat', { ...payload, stream: false }, { timeout: 180_000 })
  },
  listConversations(params: ConversationQuery = {}) {
    return request.get<PageData<Conversation>>('/conversations', { params })
  },
  createConversation(payload: Partial<Conversation> = {}) {
    return request.post<Conversation>('/conversations', payload)
  },
  getConversation(id: number) {
    return request.get<Conversation>(`/conversations/${id}`)
  },
  updateConversation(id: number, payload: Partial<Conversation>) {
    return request.put<Conversation>(`/conversations/${id}`, payload)
  },
  deleteConversation(id: number) {
    return request.delete<{ message: string }>(`/conversations/${id}`)
  },
  clearConversation(id: number) {
    return request.post<Conversation>(`/conversations/${id}/clear`)
  },
  listMessages(id: number, params: { limit?: number; before_id?: number } = {}) {
    return request.get<ChatMessage[]>(`/conversations/${id}/messages`, { params })
  },
  deleteMessage(id: number) {
    return request.delete<{ message: string }>(`/messages/${id}`)
  },
}
