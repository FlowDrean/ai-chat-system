/** 技能（Skills）接口 */
import { request } from './request'
import type {
  PageData,
  PageQuery,
  SkillItem,
  SkillOption,
  SkillPayload,
  SkillSpec,
  SkillTestResult,
} from '@/types'

export interface SkillQuery extends PageQuery {
  keyword?: string
  type?: string
  enabled?: boolean
}

export const skillApi = {
  /** 管理列表（管理员） */
  list(params: SkillQuery = {}) {
    return request.get<PageData<SkillItem>>('/skills', { params: { page_size: 100, ...params } })
  },
  /** 技能类型规格（动态表单） */
  specs() {
    return request.get<SkillSpec[]>('/skills/specs')
  },
  /** 聊天可用的技能（任意登录用户） */
  available() {
    return request.get<SkillOption[]>('/skills/available')
  },
  get(id: number) {
    return request.get<SkillItem>(`/skills/${id}`)
  },
  create(payload: SkillPayload) {
    return request.post<SkillItem>('/skills', payload)
  },
  update(id: number, payload: Partial<SkillPayload>) {
    return request.put<SkillItem>(`/skills/${id}`, payload)
  },
  remove(id: number) {
    return request.delete<{ message: string }>(`/skills/${id}`)
  },
  toggle(id: number, enabled: boolean) {
    return request.patch<SkillItem>(`/skills/${id}/enabled`, undefined, { params: { enabled } })
  },
  /** 试运行已保存的技能 */
  test(id: number, args: Record<string, unknown> = {}, config?: Record<string, unknown>) {
    return request.post<SkillTestResult>(`/skills/${id}/test`, { arguments: args, config }, { timeout: 120_000 })
  },
  /** 未保存的配置也能试运行 */
  testDraft(type: string, args: Record<string, unknown> = {}, config?: Record<string, unknown>) {
    return request.post<SkillTestResult>(
      '/skills/test-run',
      { arguments: args, config },
      { params: { skill_type: type }, timeout: 120_000 },
    )
  },
}
