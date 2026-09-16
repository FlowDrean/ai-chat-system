/** 用户管理接口 */
import { request } from './request'
import type { PageData, PageQuery, UserInfo } from '@/types'

export interface UserQuery extends PageQuery {
  keyword?: string
  role?: string
  status?: number
}

export interface UserPayload {
  username?: string
  password?: string
  email?: string | null
  nickname?: string | null
  role?: 'user' | 'admin'
  status?: number
  avatar?: string | null
}

export const userApi = {
  list(params: UserQuery = {}) {
    return request.get<PageData<UserInfo>>('/users', { params })
  },
  create(payload: UserPayload) {
    return request.post<UserInfo>('/users', payload)
  },
  update(id: number, payload: UserPayload) {
    return request.put<UserInfo>(`/users/${id}`, payload)
  },
  remove(id: number) {
    return request.delete<{ message: string }>(`/users/${id}`)
  },
  resetPassword(id: number, newPassword: string) {
    return request.post<{ message: string }>(`/users/${id}/reset-password`, { new_password: newPassword })
  },
  profile() {
    return request.get<UserInfo>('/profile')
  },
  updateProfile(payload: UserPayload) {
    return request.put<UserInfo>('/profile', payload)
  },
}
