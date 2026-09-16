/** Markdown 渲染：marked + highlight.js + DOMPurify(XSS 清洗) */
import DOMPurify from 'dompurify'
import hljs from 'highlight.js'
import { Marked } from 'marked'

import 'highlight.js/styles/github.css'

const marked = new Marked({
  gfm: true,
  breaks: true,
})

marked.use({
  renderer: {
    // marked v12+ 的 renderer 接收 token 对象
    code(token: { text: string; lang?: string }) {
      const language = (token.lang || '').trim().split(/\s+/)[0]
      let highlighted: string
      try {
        highlighted =
          language && hljs.getLanguage(language)
            ? hljs.highlight(token.text, { language, ignoreIllegals: true }).value
            : hljs.highlightAuto(token.text).value
      } catch {
        highlighted = escapeHtml(token.text)
      }
      return (
        '<div class="code-block">' +
        '<div class="code-block__header">' +
        `<span class="code-block__lang">${escapeHtml(language || 'text')}</span>` +
        '<button type="button" class="code-block__copy" data-role="copy">复制</button>' +
        '</div>' +
        `<pre class="hljs"><code class="language-${escapeHtml(language || 'text')}">${highlighted}</code></pre>` +
        '</div>'
      )
    },
    table(token: { header: Array<{ text: string }>; rows: Array<Array<{ text: string }>> }) {
      const head = token.header.map((cell) => `<th>${cell.text}</th>`).join('')
      const body = token.rows.map((row) => `<tr>${row.map((cell) => `<td>${cell.text}</td>`).join('')}</tr>`).join('')
      return `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`
    },
  },
})

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/** Markdown 文本  安全的 HTML */
export function renderMarkdown(text?: string | null): string {
  if (!text) return ''
  const raw = marked.parse(text, { async: false }) as string
  return DOMPurify.sanitize(raw, {
    ADD_ATTR: ['target', 'rel', 'class', 'data-role'],
    FORBID_TAGS: ['style', 'iframe', 'form', 'input', 'script'],
    FORBID_ATTR: ['onerror', 'onload', 'onclick'],
  })
}

export { hljs }
