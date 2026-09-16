/** Dashboard / 系统接口 */
import { request } from './request'
import type { DashboardData } from '@/types'

export const dashboardApi = {
  overview(days = 14) {
    return request.get<DashboardData>('/dashboard', { params: { days } })
  },
  systemInfo() {
    return request.get<Record<string, unknown>>('/system/info')
  },
  health() {
    return request.get<{ status: string; version: string }>('/health')
  },
}
