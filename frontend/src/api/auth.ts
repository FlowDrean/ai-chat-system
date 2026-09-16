/** 认证接口 */
import { request } from './request'
import type { LoginPayload, LoginResult, RegisterPayload, UserInfo } from '@/types'

export const authApi = {
  login(payload: LoginPayload) {
    return request.post<LoginResult>('/auth/login', payload)
  },
  register(payload: RegisterPayload) {
    return request.post<LoginResult>('/auth/register', payload)
  },
  me() {
    return request.get<UserInfo>('/auth/me')
  },
  logout() {
    return request.post<{ message: string }>('/auth/logout')
  },
  changePassword(payload: { old_password: string; new_password: string }) {
    return request.post<{ message: string }>('/auth/password', payload)
  },
}
