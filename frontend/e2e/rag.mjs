/**
 * RAG 端到端测试（Playwright）
 *
 * 覆盖开发文档 §51 的第二条主链路：
 *   创建知识库 → 上传 PDF → 解析/切分/向量化 → 聊天选择知识库 → RAG 问答 → 显示引用来源
 *
 * 运行前请先启动后端与前端，然后执行：node e2e/rag.mjs
 */
import { chromium } from 'playwright'

const BASE = process.env.E2E_BASE_URL || 'http://127.0.0.1:5173'
const USERNAME = process.env.E2E_USERNAME || 'admin'
const PASSWORD = process.env.E2E_PASSWORD || 'admin123456'
const KB_NAME = `E2E 知识库 ${Date.now().toString().slice(-6)}`
const API_BASE = process.env.E2E_API_URL || 'http://127.0.0.1:8000/api'

let passed = 0
let failed = 0
const consoleErrors = []

function check(name, condition, detail = '') {
  if (condition) {
    passed += 1
    console.log(`  [PASS] ${name} ${detail}`)
  } else {
    failed += 1
    console.log(`  [FAIL] ${name} ${detail}`)
  }
}

/**
 * 让后续对话固定使用内置 mock 模型。
 *
 * 为什么需要：模型配置是全局共享的，如果使用者的默认模型是真实模型（如 DeepSeek），
 * 自动化测试就会消耗真实 API 额度。这里通过 localStorage 把会话默认模型指向 mock，
 * 保证测试「零成本、可重复、结果稳定」。
 */
async function preferMockModel(page) {
  const token = await page.evaluate(() => localStorage.getItem('ai_chat_token'))
  if (!token) return null
  const res = await fetch(`${API_BASE}/models?page_size=100`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const body = await res.json()
  const mock = (body.data?.items || []).find((m) => m.provider === 'mock' && m.enabled)
  if (!mock) {
    console.log('    （未找到 mock 模型，将使用默认模型）')
    return null
  }
  await page.evaluate((id) => {
    const raw = localStorage.getItem('ai_chat_settings')
    const state = raw ? JSON.parse(raw) : {}
    state.modelId = id
    localStorage.setItem('ai_chat_settings', JSON.stringify(state))
  }, mock.id)
  console.log(`    已固定使用内置模型：${mock.name} (id=${mock.id})`)
  return mock
}

const browser = await chromium.launch({ channel: 'msedge', headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN' })
const page = await context.newPage()
let chatPayload = null
page.on('request', (request) => {
  if (request.url().includes('/chat/stream') && request.method() === 'POST') {
    try {
      chatPayload = JSON.parse(request.postData() || '{}')
    } catch {
      chatPayload = null
    }
  }
})
page.on('console', (msg) => {
  if (msg.type() === 'error') consoleErrors.push(msg.text())
})
page.on('pageerror', (error) => consoleErrors.push(`pageerror: ${error.message}`))

try {
  /* ------------------------------------------------------------ 登录 */
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' })
  await page.fill('input[autocomplete="username"]', USERNAME)
  await page.fill('input[autocomplete="current-password"]', PASSWORD)
  await page.click('button[type="submit"]')
  await page.waitForURL('**/chat', { timeout: 15000 })
  await preferMockModel(page)
  await page.reload({ waitUntil: 'networkidle' })
  console.log('\n[1] 登录完成')

  /* ------------------------------------------------------------ 创建知识库 */
  console.log('[2] 通过界面创建知识库')
  await page.goto(`${BASE}/admin/knowledge`, { waitUntil: 'networkidle' })
  await page.click('button:has-text("新建知识库")')
  await page.waitForSelector('.ant-modal-content', { timeout: 8000 })
  await page.fill('.ant-modal-content input[placeholder="例如：产品说明书"]', KB_NAME)
  await page.click('.ant-modal-footer .ant-btn-primary')
  await page.waitForTimeout(1500)
  const created = await page.locator(`.knowledge-card:has-text("${KB_NAME}")`).count()
  check('知识库创建成功并出现在列表中', created > 0, KB_NAME)

  /* ------------------------------------------------------------ 进入详情并上传 PDF */
  console.log('[3] 上传文档并等待向量化')
  await page.click(`.knowledge-card:has-text("${KB_NAME}")`)
  await page.waitForURL('**/admin/knowledge/**', { timeout: 10000 })
  await page.waitForTimeout(800)

  await page.setInputFiles('input[type="file"]', 'e2e/fixtures/fastapi-note.pdf')
  await page.waitForTimeout(1500)

  // 等待状态变为「处理完成」
  let completed = false
  for (let i = 0; i < 30; i += 1) {
    const text = (await page.textContent('.document-list')) || ''
    if (text.includes('处理完成')) {
      completed = true
      break
    }
    if (text.includes('处理失败')) break
    await page.waitForTimeout(1000)
  }
  check('文档完成解析与向量化', completed)

  const tableText = (await page.textContent('.document-list')) || ''
  check('文档列表显示分块数量', /处理完成/.test(tableText), tableText.replace(/\s+/g, ' ').slice(0, 120))

  /* ------------------------------------------------------------ 检索测试 */
  console.log('[4] 知识库检索测试')
  await page.click('button:has-text("检索测试")')
  await page.waitForTimeout(500)
  const testInput = '.ant-modal-content input[placeholder="输入问题，验证召回效果"]'
  await page.fill(testInput, 'FastAPI 是不是异步框架？')
  await page.press(testInput, 'Enter')
  await page.waitForTimeout(2500)
  const testText = (await page.textContent('.ant-modal-content')) || ''
  check('检索测试命中内容', testText.includes('相似度'), testText.includes('没有检索到内容') ? '未命中' : '')
  await page.keyboard.press('Escape')
  await page.waitForTimeout(500)

  /* ------------------------------------------------------------ RAG 聊天 */
  console.log('[5] RAG 问答（带引用来源）')
  await page.goto(`${BASE}/chat`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1200)

  // 在顶部选择知识库（第二个下拉框）
  await page.locator('.chat-header__right .ant-select').nth(1).click()
  await page.waitForTimeout(400)
  await page.click(`.ant-select-item-option:has-text("${KB_NAME}")`)
  await page.waitForTimeout(600)

  // 用与文档词面重合度较高的问题，保证本地轻量 Embedding 能召回（真实语义模型下无此限制）
  await page.fill('textarea', 'Which frameworks is FastAPI built on and does it support async handlers?')
  await page.keyboard.press('Enter')
  await page.waitForTimeout(1500)
  check(
    '聊天请求携带 knowledge_base_id（已进入 RAG 流程）',
    Boolean(chatPayload && chatPayload.knowledge_base_id),
    JSON.stringify(chatPayload),
  )

  await page.waitForSelector('.chat-message.is-assistant .markdown-body', { timeout: 30000 })
  await page.waitForSelector('.rag-source__item', { timeout: 30000 })
  const sources = await page.locator('.rag-source__item').count()
  check('AI 回复展示了引用来源', sources >= 1, `${sources} 条引用`)

  const sourceText = (await page.textContent('.rag-source')) || ''
  check('引用来源包含文件名与相似度', sourceText.includes('相似度'), sourceText.replace(/\s+/g, ' ').slice(0, 140))

  // 点击引用查看详情
  await page.click('.rag-source__item')
  await page.waitForSelector('.ant-drawer-open', { timeout: 8000 })
  const drawerText = (await page.textContent('.ant-drawer')) || ''
  check('引用详情抽屉包含 Chunk 内容与 Metadata', drawerText.includes('Chunk 内容') && drawerText.includes('相似度'))

  const serious = consoleErrors.filter(
    (text) => !text.includes('favicon') && !text.includes('Download the Vue Devtools'),
  )
  check('无严重控制台错误', serious.length === 0, serious.slice(0, 3).join(' | '))

  /* ------------------------------------------------------------ 清理测试数据 */
  const token = await page.evaluate(() => localStorage.getItem('ai_chat_token'))
  if (token) {
    const headers = { Authorization: `Bearer ${token}` }
    const listRes = await fetch(`${API_BASE}/knowledge-bases?page_size=100`, { headers })
    const list = await listRes.json()
    for (const kb of list.data?.items || []) {
      if (kb.name.startsWith('E2E 知识库')) {
        await fetch(`${API_BASE}/knowledge-bases/${kb.id}`, { method: 'DELETE', headers })
        console.log(`  已清理测试知识库：${kb.name}`)
      }
    }
  }

  console.log('\n' + '='.repeat(66))
  console.log(`RAG E2E 结果：通过 ${passed} 项，失败 ${failed} 项`)
  console.log('='.repeat(66))
} catch (error) {
  failed += 1
  console.error('\n[RAG E2E 异常]', error.message)
  await page.screenshot({ path: 'e2e-rag-failure.png', fullPage: true }).catch(() => undefined)
} finally {
  await browser.close()
}

process.exit(failed === 0 ? 0 : 1)
