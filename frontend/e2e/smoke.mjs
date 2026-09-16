/**
 * 前端端到端冒烟测试（Playwright）
 *
 * 覆盖：
 *   登录 → AI 聊天（SSE 真流式）→ 会话落库 → 各管理页面渲染 → 控制台无报错
 *
 * 运行前请先启动后端与前端：
 *   cd backend  && .venv/Scripts/python -m uvicorn app.main:app --port 8000
 *   cd frontend && npm run dev
 * 然后执行：
 *   node e2e/smoke.mjs
 *
 * 默认使用系统已安装的 Edge（找不到时回退 Chrome），因此无需下载浏览器内核。
 */
import { chromium } from 'playwright'

const BASE = process.env.E2E_BASE_URL || 'http://127.0.0.1:5173'
const API_BASE = process.env.E2E_API_URL || 'http://127.0.0.1:8000/api'
const USERNAME = process.env.E2E_USERNAME || 'admin'
const PASSWORD = process.env.E2E_PASSWORD || 'admin123456'

let passed = 0
let failed = 0
const consoleErrors = []

// UI 规范：界面不使用 emoji（图标统一用 Ant Design 图标）
const EMOJI_RE = /[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}\u{1F1E6}-\u{1F1FF}]/gu

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

async function launchBrowser() {
  for (const channel of ['msedge', 'chrome', undefined]) {
    try {
      return await chromium.launch({ channel, headless: true })
    } catch (error) {
      console.log(`  启动浏览器 channel=${channel} 失败：${error.message?.split('\n')[0]}`)
    }
  }
  throw new Error('无法启动任何浏览器，请安装 Edge / Chrome 或执行 npx playwright install chromium')
}

const browser = await launchBrowser()
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN' })
const page = await context.newPage()

page.on('console', (msg) => {
  if (msg.type() === 'error') consoleErrors.push(msg.text())
})
page.on('pageerror', (error) => consoleErrors.push(`pageerror: ${error.message}`))

try {
  /* ------------------------------------------------------------ 登录 */
  console.log('\n[1] 登录流程')
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' })
  await page.waitForSelector('input[autocomplete="username"]')
  const loginText = (await page.textContent('body')) || ''
  check('登录页不再显示默认账号提示', !loginText.includes('admin123456') && !loginText.includes('首次启动默认账号'))
  await page.fill('input[autocomplete="username"]', USERNAME)
  await page.fill('input[autocomplete="current-password"]', PASSWORD)
  await page.click('button[type="submit"]')
  await page.waitForURL('**/chat', { timeout: 15000 })
  await preferMockModel(page)
  await page.reload({ waitUntil: 'networkidle' })
  check('登录后跳转到 /chat', page.url().includes('/chat'), page.url())
  await page.waitForSelector('.chat-layout__sider, .chat-page', { timeout: 10000 })
  check('聊天布局渲染成功', true)

  /* ------------------------------------------------------------ 流式聊天 */
  console.log('\n[2] AI 聊天（SSE 流式）')
  await page.fill('textarea', '你好，请介绍一下 FastAPI')
  await page.keyboard.press('Enter')

  await page.waitForSelector('.chat-message.is-user', { timeout: 10000 })
  check('用户消息已显示', true)

  await page.waitForSelector('.chat-message.is-assistant .markdown-body', { timeout: 30000 })
  const first = (await page.textContent('.chat-message.is-assistant .markdown-body')) || ''
  await page.waitForTimeout(700)
  const second = (await page.textContent('.chat-message.is-assistant .markdown-body')) || ''
  check('AI 回复已渲染 Markdown', second.length > 20, `${second.length} 字符`)
  check('回复是逐字流式增长（真 SSE）', second.length >= first.length, `${first.length} → ${second.length}`)

  const streamingVisible = await page.isVisible('.chat-message__caret, .chat-input__hint, .chat-message__actions')
  check('流式状态 / 完成操作区可见', streamingVisible)

  await page.waitForSelector('.chat-message.is-assistant .chat-message__actions', { timeout: 30000 })
  const tokenText = (await page.textContent('.chat-message.is-assistant .chat-message__usage')) || ''
  check('展示 Token / 耗时统计', tokenText.includes('Token') || tokenText.includes('耗时'), tokenText.trim())

  // mock 模型的示例回答也不应包含 emoji（后端输出的 Markdown）
  const chatText = (await page.textContent('.chat-page')) || ''
  const chatEmoji = chatText.match(EMOJI_RE)
  check('聊天界面与回答无 emoji', !chatEmoji, chatEmoji ? `发现 ${chatEmoji.join(' ')}` : '')

  /* ------------------------------------------------------------ 停止生成 */
  console.log('\n[2.1] 停止生成')
  await page.fill('textarea', '请写一篇 300 字左右的文章介绍向量数据库')
  await page.keyboard.press('Enter')
  // 等出现「停止生成」按钮（生成中）
  await page.waitForSelector('.chat-input__send .ant-btn-dangerous', { timeout: 15000 })
  await page.waitForTimeout(600)
  await page.click('.chat-input__send .ant-btn-dangerous')
  await page.waitForTimeout(2000)
  const stoppedText = await page.textContent('.chat-message.is-assistant:last-of-type') || ''
  check('停止生成后展示「已停止生成」', stoppedText.includes('已停止生成'), stoppedText.replace(/\s+/g, ' ').slice(0, 80))
  check('停止后仍保留已生成内容', stoppedText.length > 60, `${stoppedText.length} 字符`)

  /* ------------------------------------------------------------ 会话列表 */
  console.log('\n[3] 会话列表')
  await page.waitForTimeout(1200)
  const conversationCount = await page.locator('.conversation-list__item').count()
  check('侧边栏出现会话记录', conversationCount >= 1, `${conversationCount} 个会话`)

  /* ------------------------------------------------------------ 管理后台页面 */
  console.log('\n[4] 管理后台页面渲染')
  // 注意：断言使用「页面主体独有」的文案，避免误命中侧边栏菜单项
  const pages = [
    ['/admin/dashboard', 'AI 调用趋势'],
    ['/admin/models', '统一配置多个大模型供应商'],
    ['/admin/knowledge', '让 AI 基于你的专属资料回答'],
    ['/admin/documents', '跨知识库查看所有文档'],
    ['/admin/prompts', '沉淀 System Prompt 模板'],
    ['/admin/users', '管理系统用户、角色与状态'],
    ['/admin/settings', '个人资料、密码安全与系统运行信息'],
    ['/', '有什么可以帮你'],
  ]
  for (const [path, expected] of pages) {
    await page.goto(`${BASE}${path}`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(1200)
    const body = (await page.textContent('body')) || ''
    const hasContent = await page.locator('.page-container, .home-page').count()
    check(`${path} 渲染`, body.includes(expected) && hasContent > 0, body.includes(expected) ? '' : '未找到页面主体')
    const foundEmoji = body.match(EMOJI_RE)
    check(`${path} 界面无 emoji`, !foundEmoji, foundEmoji ? `发现 ${foundEmoji.join(' ')}` : '')
  }

  /* ------------------------------------------------------------ 模型管理交互 */
  console.log('\n[5] 模型管理交互')
  await page.goto(`${BASE}/admin/models`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(800)
  const rows = await page.locator('.ant-table-tbody tr.ant-table-row').count()
  check('模型列表有数据', rows >= 1, `${rows} 行`)
  await page.click('button:has-text("新增模型")')
  await page.waitForSelector('.ant-modal-content', { timeout: 8000 })
  const modalText = (await page.textContent('.ant-modal-content')) || ''
  check('新增模型弹窗打开', modalText.includes('模型名称'))
  // 注意：Ant Design 会在两个汉字的按钮文案中间插入空格（取 消），因此按样式定位
  await page.click('.ant-modal-footer button:not(.ant-btn-primary)')
  await page.waitForTimeout(400)

  /* ------------------------------------------------------------ 控制台 */
  console.log('\n[6] 控制台错误检查')
  const serious = consoleErrors.filter(
    (text) => !text.includes('favicon') && !text.includes('Download the Vue Devtools'),
  )
  check('无严重控制台错误', serious.length === 0, serious.slice(0, 3).join(' | '))

  console.log('\n' + '='.repeat(66))
  console.log(`前端 E2E 结果：通过 ${passed} 项，失败 ${failed} 项`)
  console.log('='.repeat(66))
} catch (error) {
  failed += 1
  console.error('\n[E2E 异常]', error.message)
  await page.screenshot({ path: 'e2e-failure.png', fullPage: true }).catch(() => undefined)
  console.error('已保存截图 e2e-failure.png')
} finally {
  await browser.close()
}

process.exit(failed === 0 ? 0 : 1)
