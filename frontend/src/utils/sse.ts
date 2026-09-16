/**
 * SSE 流式聊天客户端
 *
 * 为什么不用 EventSource？
 * - 官方 EventSource 只能发 GET、不能自定义请求头（无法带 Bearer Token）、不能中断。
 * 因此这里使用 fetch + ReadableStream 手工解析 SSE 帧，支持：
 *   POST 请求体 / Authorization 头 / AbortController 中断（停止生成）
 */
import { getToken } from '@/api/request'
import type { ChatRequestPayload, StreamEvent } from '@/types'

export interface StreamHandlers {
  onStart?: (event: StreamEvent) => void
  onMeta?: (event: StreamEvent) => void
  onRoute?: (event: StreamEvent) => void
  onSources?: (event: StreamEvent) => void
  onSkill?: (event: StreamEvent) => void
  onToken?: (content: string, event: StreamEvent) => void
  onNotice?: (event: StreamEvent) => void
  onError?: (event: StreamEvent) => void
  onDone?: (event: StreamEvent) => void
}

function dispatch(event: StreamEvent, handlers: StreamHandlers): void {
  switch (event.type) {
    case 'start':
      handlers.onStart?.(event)
      break
    case 'meta':
      handlers.onMeta?.(event)
      break
    case 'route':
      handlers.onRoute?.(event)
      break
    case 'sources':
      handlers.onSources?.(event)
      break
    case 'skill':
      handlers.onSkill?.(event)
      break
    case 'token':
      handlers.onToken?.(String(event.content ?? ''), event)
      break
    case 'notice':
    case 'usage':
      handlers.onNotice?.(event)
      break
    case 'error':
      handlers.onError?.(event)
      break
    case 'done':
      handlers.onDone?.(event)
      break
    default:
      break
  }
}

/**
 * 发起一次流式聊天。
 *
 * @returns Promise 在流结束时 resolve；被中断时 reject AbortError
 */
export async function streamChat(
  payload: ChatRequestPayload,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const token = getToken()
  const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || '/api'}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ ...payload, stream: true }),
    signal,
  })

  if (!response.ok) {
    // 统一错误结构：{ code, message, data }
    let text = `请求失败（HTTP ${response.status}）`
    try {
      const body = await response.json()
      text = body?.message || text
      if (response.status === 401) {
        text = body?.message || '登录已过期，请重新登录'
      }
    } catch {
      /* 忽略解析失败 */
    }
    throw new Error(text)
  }

  if (!response.body) {
    throw new Error('当前浏览器不支持流式响应')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  try {
    for (;;) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      const frames = buffer.split('\n\n')
      buffer = frames.pop() ?? ''

      for (const frame of frames) {
        const dataLines = frame
          .split('\n')
          .filter((line) => line.startsWith('data:'))
          .map((line) => line.slice(5).trimStart())
        if (!dataLines.length) continue
        const raw = dataLines.join('\n')
        if (!raw) continue
        try {
          dispatch(JSON.parse(raw) as StreamEvent, handlers)
        } catch (error) {
          console.warn('[SSE] 无法解析事件', raw, error)
        }
      }
    }
  } finally {
    reader.releaseLock?.()
  }
}
