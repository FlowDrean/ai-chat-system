/** 格式化工具 */
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'

dayjs.locale('zh-cn')
dayjs.extend(relativeTime)

export function formatDateTime(value?: string | null, template = 'YYYY-MM-DD HH:mm'): string {
  if (!value) return '-'
  return dayjs(value).format(template)
}

export function formatRelative(value?: string | null): string {
  if (!value) return '-'
  const target = dayjs(value)
  if (target.isAfter(dayjs().subtract(1, 'minute'))) return '刚刚'
  return target.fromNow()
}

/** 会话列表分组：今天 / 昨天 / 更早 */
export function groupByDay<T extends { updated_at?: string | null; created_at?: string | null }>(
  items: T[],
): Array<{ label: string; items: T[] }> {
  const today = dayjs().startOf('day')
  const yesterday = today.subtract(1, 'day')
  const sevenDaysAgo = today.subtract(7, 'day')

  const buckets: Record<string, T[]> = { '今天': [], '昨天': [], '近 7 天': [], '更早': [] }
  items.forEach((item) => {
    const time = dayjs(item.updated_at || item.created_at)
    if (time.isAfter(today)) buckets['今天'].push(item)
    else if (time.isAfter(yesterday)) buckets['昨天'].push(item)
    else if (time.isAfter(sevenDaysAgo)) buckets['近 7 天'].push(item)
    else buckets['更早'].push(item)
  })
  return Object.entries(buckets)
    .filter(([, list]) => list.length > 0)
    .map(([label, list]) => ({ label, items: list }))
}

export function formatFileSize(bytes?: number | null): string {
  if (!bytes || bytes <= 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let value = bytes
  let index = 0
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024
    index += 1
  }
  return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${units[index]}`
}

export function formatNumber(value?: number | null): string {
  if (value == null) return '0'
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
  if (value >= 10_000) return `${(value / 1000).toFixed(1)}K`
  return value.toLocaleString('zh-CN')
}

export function formatDuration(ms?: number | null): string {
  if (!ms || ms < 0) return '-'
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

/** 文档处理状态  展示文案 / 颜色 */
/**
 * 文档处理状态：黑白主题下只用「中性 tag + 状态点颜色」表达，
 * 因此 color 统一为 default，真正的语义色由 dot 决定。
 */
export const DOCUMENT_STATUS_MAP: Record<
  string,
  { text: string; color: string; dot: 'ok' | 'warn' | 'error' | '' }
> = {
  pending: { text: '等待处理', color: 'default', dot: '' },
  parsing: { text: '解析中', color: 'default', dot: 'warn' },
  splitting: { text: '切分中', color: 'default', dot: 'warn' },
  embedding: { text: '向量化中', color: 'default', dot: 'warn' },
  completed: { text: '处理完成', color: 'default', dot: 'ok' },
  failed: { text: '处理失败', color: 'default', dot: 'error' },
}


export function documentStatusDot(status?: string | null): string {
  return DOCUMENT_STATUS_MAP[status || 'pending']?.dot || ''
}

export function documentStatusText(status?: string | null): string {
  return DOCUMENT_STATUS_MAP[status || 'pending']?.text || '未知状态'
}

/**
 * 黑白主题下，供应商标签不再使用彩色，统一走中性样式。
 * 保留这个映射是为了兼容既有调用点（返回 'default' 表示使用默认灰色 tag）。
 */
export const PROVIDER_COLORS: Record<string, string> = {
  openai: 'default',
  deepseek: 'default',
  qwen: 'default',
  ollama: 'default',
  gemini: 'default',
  claude: 'default',
  moonshot: 'default',
  zhipu: 'default',
  siliconflow: 'default',
  custom: 'default',
  mock: 'default',
}

export function copyToClipboard(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    return navigator.clipboard.writeText(text)
  }
  return new Promise((resolve, reject) => {
    try {
      const textarea = document.createElement('textarea')
      textarea.value = text
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
      resolve()
    } catch (error) {
      reject(error)
    }
  })
}
