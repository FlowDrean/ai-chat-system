/**
 * Axios 统一封装
 * - 自动注入 Bearer Token
 * - 自动拆包 { code, message, data }
 * - 统一错误提示 & 401 处理
 */
import axios, { type AxiosError, type AxiosInstance, type AxiosRequestConfig } from 'axios'
import { message } from 'ant-design-vue'

import type { ApiEnvelope } from '@/types'

const TOKEN_KEY = 'ai_chat_token'

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token)
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY)
}

/** 业务异常：携带后端返回的 code / message */
export class ApiError extends Error {
  code: number
  status?: number

  constructor(code: number, msg: string, status?: number) {
    super(msg)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

const instance: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api',
  timeout: 60_000,
  headers: { 'Content-Type': 'application/json' },
})

instance.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers = config.headers ?? {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

let redirecting = false

function handleUnauthorized(msg: string): void {
  clearToken()
  if (!redirecting && !location.pathname.startsWith('/login')) {
    redirecting = true
    message.warning(msg || '登录已过期，请重新登录')
    setTimeout(() => {
      location.href = `/login?redirect=${encodeURIComponent(location.pathname + location.search)}`
      redirecting = false
    }, 600)
  }
}

instance.interceptors.response.use(
  (response) => {
    const body = response.data as ApiEnvelope
    // 文件下载等非标准响应直接返回原始数据
    if (body == null || typeof body !== 'object' || !('code' in body)) {
      return response.data
    }
    if (body.code === 0) {
      return body.data
    }
    const error = new ApiError(body.code, body.message || '请求失败', response.status)
    if (error.code === 40100 || error.code === 40101 || error.code === 40102) {
      handleUnauthorized(error.message)
    } else {
      message.error(error.message)
    }
    return Promise.reject(error)
  },
  (error: AxiosError<ApiEnvelope>) => {
    const status = error.response?.status
    const body = error.response?.data
    const code = body?.code ?? status ?? -1
    let text = body?.message || error.message || '网络异常，请稍后重试'

    if (status === 401 || code === 40100) {
      handleUnauthorized(body?.message || '登录已过期，请重新登录')
    } else if (status === 403) {
      text = body?.message || '没有操作权限'
      message.error(text)
    } else if (status && status >= 500) {
      message.error(text || '服务器内部错误')
    } else if (error.code === 'ECONNABORTED') {
      text = '请求超时，请稍后重试'
      message.error(text)
    } else if (!error.response) {
      text = '网络连接失败，请检查后端服务是否启动'
      message.error(text)
    } else {
      message.error(text)
    }
    return Promise.reject(new ApiError(Number(code) || -1, text, status))
  },
)

/** 统一请求方法：返回值已解开 data 字段 */
export const request = {
  get<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return instance.get(url, config) as unknown as Promise<T>
  },
  post<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return instance.post(url, data, config) as unknown as Promise<T>
  },
  put<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return instance.put(url, data, config) as unknown as Promise<T>
  },
  patch<T = unknown>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    return instance.patch(url, data, config) as unknown as Promise<T>
  },
  delete<T = unknown>(url: string, config?: AxiosRequestConfig): Promise<T> {
    return instance.delete(url, config) as unknown as Promise<T>
  },
  upload<T = unknown>(url: string, formData: FormData, config?: AxiosRequestConfig): Promise<T> {
    return instance.post(url, formData, {
      ...config,
      headers: { 'Content-Type': 'multipart/form-data', ...(config?.headers || {}) },
      timeout: 120_000,
    }) as unknown as Promise<T>
  },
}

export default instance
