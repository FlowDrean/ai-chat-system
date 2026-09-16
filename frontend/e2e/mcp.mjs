/**
 * MCP 管理端到端测试（Playwright）
 *
 * 覆盖完整闭环：
 *   MCP 管理页接入 stdio 服务 → 连接测试并发现工具 → 查看工具清单（JSON Schema）
 *   → 聊天页勾选 MCP 服务 → 模型调用 MCP 工具 → 展示调用记录（MCP 标识）
 *   → 会话级记忆 → 清理
 *
 * 前置：后端已启动；本机会用 backend/.venv 的 python 拉起 scripts/demo_mcp_server.py。
 * 运行：node e2e/mcp.mjs
 */
import path from 'node:path'
import { chromium } from 'playwright'

const BASE = process.env.E2E_BASE_URL || 'http://127.0.0.1:5173'
const API_BASE = process.env.E2E_API_URL || 'http://127.0.0.1:8000/api'
const USERNAME = process.env.E2E_USERNAME || 'admin'
const PASSWORD = process.env.E2E_PASSWORD || 'admin123456'
const SERVER_NAME = `E2E MCP 服务 ${Date.now().toString().slice(-5)}`
const IMPORT_KEY = `E2E导入-amap-maps-${Date.now().toString().slice(-4)}`

const BACKEND_DIR = path.resolve(process.cwd(), '../backend')
const MCP_COMMAND = process.env.E2E_MCP_COMMAND || path.join(BACKEND_DIR, '.venv', 'Scripts', 'python.exe')

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

/** 固定使用内置 mock 模型（避免消耗真实额度，且 mock 支持确定性触发 MCP 工具） */
async function preferMockModel(page) {
  const token = await page.evaluate(() => localStorage.getItem('ai_chat_token'))
  const res = await fetch(`${API_BASE}/models?page_size=100`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const body = await res.json()
  const mock = (body.data?.items || []).find((m) => m.provider === 'mock' && m.enabled)
  if (!mock) return null
  await page.evaluate((id) => {
    const raw = localStorage.getItem('ai_chat_settings')
    const state = raw ? JSON.parse(raw) : {}
    state.modelId = id
    state.skillIds = []
    state.mcpServerIds = []
    localStorage.setItem('ai_chat_settings', JSON.stringify(state))
  }, mock.id)
  return mock
}

const browser = await chromium.launch({ channel: 'msedge', headless: true })
const context = await browser.newContext({ viewport: { width: 1500, height: 950 }, locale: 'zh-CN' })
const page = await context.newPage()
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
  const mock = await preferMockModel(page)
  console.log(`\n[1] 登录完成（模型固定为 ${mock?.name || '默认模型'}）`)

  /* ------------------------------------------------------------ 清理历史遗留 */
  const tokenForCleanup = await page.evaluate(() => localStorage.getItem('ai_chat_token'))
  if (tokenForCleanup) {
    const headers = { Authorization: `Bearer ${tokenForCleanup}` }
    const existing = await fetch(`${API_BASE}/mcp/servers?page_size=100`, { headers })
    const body = await existing.json()
    for (const item of body.data?.items || []) {
      if (item.name.startsWith('E2E MCP 服务') || item.name.startsWith('E2E导入')) {
        await fetch(`${API_BASE}/mcp/servers/${item.id}`, { method: 'DELETE', headers })
        console.log(`  清理历史遗留服务：${item.name}`)
      }
    }
  }

  /* ------------------------------------------------------------ 接入 MCP 服务 */
  console.log('[2] 接入 MCP 服务（stdio）')
  await page.goto(`${BASE}/admin/mcp`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1200)
  const pageText = (await page.textContent('.page-container')) || ''
  check('MCP 管理页渲染', pageText.includes('MCP 管理') && pageText.includes('支持的传输方式'))
  check('展示三种传输方式', pageText.includes('本地进程') && pageText.includes('远程 SSE') && pageText.includes('Streamable HTTP'))

  await page.click('button:has-text("接入 MCP 服务")')
  await page.waitForSelector('.ant-drawer-open', { timeout: 8000 })
  await page.waitForTimeout(700)

  await page.fill('.ant-drawer-open input[placeholder="例如：文件系统 / GitHub"]', SERVER_NAME)
  const commandInput = page
    .locator('.ant-drawer-open .ant-form-item')
    .filter({ hasText: '启动命令' })
    .locator('input')
  await commandInput.fill(MCP_COMMAND)
  const argsInput = page
    .locator('.ant-drawer-open .ant-form-item')
    .filter({ hasText: '命令参数' })
    .locator('input')
  await argsInput.fill('scripts/demo_mcp_server.py')
  await argsInput.press('Enter')
  const cwdInput = page
    .locator('.ant-drawer-open .ant-form-item')
    .filter({ hasText: '工作目录' })
    .locator('input')
  await cwdInput.fill(BACKEND_DIR)

  await page.locator('.ant-drawer-open .ant-btn-primary').last().click()
  await page.waitForTimeout(2000)
  const listText = (await page.textContent('.page-container')) || ''
  check('服务创建成功并出现在列表', listText.includes(SERVER_NAME))
  check('新建服务状态为未测试', listText.includes('未测试'))

  /* ------------------------------------------------------------ 连接测试 + 工具发现 */
  console.log('[3] 连接测试与工具发现')
  const row = page.locator('.ant-table-tbody tr.ant-table-row', { hasText: SERVER_NAME }).first()
  await row.locator('td').last().locator('button').first().click()
  await page.waitForTimeout(4000)
  const afterTest = (await page.textContent('.page-container')) || ''
  check('连接测试成功并发现工具', afterTest.includes('正常') && afterTest.includes('个工具'),
    afterTest.includes('异常') ? '状态为异常' : '')

  const toolRow = page.locator('.ant-table-tbody tr.ant-table-row', { hasText: SERVER_NAME }).first()
  await toolRow.locator('button:has-text("个工具")').click()
  await page.waitForTimeout(1000)
  const toolsText = (await page.textContent('.ant-drawer-open')) || ''
  check('工具清单包含 add / echo / text_stats',
    toolsText.includes('add') && toolsText.includes('echo') && toolsText.includes('text_stats'))
  check('工具清单展示 JSON Schema', toolsText.includes('default') || toolsText.includes('properties'))
  await page.keyboard.press('Escape')
  await page.waitForTimeout(500)

  /* ------------------------------------------------------------ 聊天中调用 MCP 工具 */
  console.log('[4] 聊天中调用 MCP 工具')
  await page.goto(`${BASE}/chat`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1200)
  await page.click('.chat-input .tool-btn:has(.anticon-api)')
  await page.waitForTimeout(800)
  const panelText = (await page.textContent('.mcp-selector__panel')) || ''
  check('MCP 选择器展示可用服务', panelText.includes(SERVER_NAME))
  check('展示工具数量', /\d+ 工具/.test(panelText), panelText.replace(/\s+/g, ' ').slice(0, 80))
  await page.click(`.mcp-selector__item:has-text("${SERVER_NAME}") .ant-checkbox-input`)
  await page.waitForTimeout(400)
  await page.keyboard.press('Escape')
  await page.waitForTimeout(400)

  await page.fill('textarea', '请用 add 工具计算 123+456')
  await page.keyboard.press('Enter')
  await page.waitForSelector('.chat-message.is-assistant .markdown-body', { timeout: 40000 })
  await page.waitForSelector('.skill-call', { timeout: 40000 })
  await page.click('.skill-call__head')
  await page.waitForTimeout(600)
  const callText = (await page.textContent('.skill-call')) || ''
  check('调用记录带 MCP 标识', callText.includes('MCP'))
  check('展示 MCP 工具结果', callText.includes('579'), callText.replace(/\s+/g, ' ').slice(0, 120))
  const answer = (await page.textContent('.chat-message.is-assistant .markdown-body')) || ''
  check('回答引用 MCP 工具结果', answer.includes('579'), answer.replace(/\s+/g, ' ').slice(0, 80))

  /* ------------------------------------------------------------ 会话级记忆 */
  console.log('[5] 会话级记忆')
  await page.reload({ waitUntil: 'networkidle' })
  await page.waitForTimeout(1500)
  const token = await page.evaluate(() => localStorage.getItem('ai_chat_token'))
  const convRes = await fetch(`${API_BASE}/conversations?page_size=1`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const convBody = await convRes.json()
  const latest = convBody.data?.items?.[0]
  check('会话持久化 mcp_server_ids', Array.isArray(latest?.mcp_server_ids) && latest.mcp_server_ids.length > 0,
    JSON.stringify(latest?.mcp_server_ids))

  /* ------------------------------------------------------------ 导入 / 导出配置 */
  console.log('[6] 导入 / 导出 mcpServers 配置')
  await page.goto(`${BASE}/admin/mcp`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1200)
  await page.click('button:has-text("导入配置")')
  await page.waitForSelector('.ant-modal-content', { timeout: 8000 })
  await page.waitForTimeout(600)

  const importPayload = JSON.stringify(
    {
      mcpServers: {
        [IMPORT_KEY]: {
          command: 'npx',
          args: ['-y', '@amap/amap-maps-mcp-server'],
          env: { AMAP_MAPS_API_KEY: '您在高德官网上申请的key' },
        },
      },
    },
    null,
    2,
  )
  await page.fill('textarea.mcp-import__editor', importPayload)
  await page.waitForTimeout(600)
  const importModalText = (await page.textContent('.ant-modal-content')) || ''
  check('预解析识别到服务数量', importModalText.includes('识别到 1 个服务'))
  check('预览展示传输方式', importModalText.includes('stdio'))
  check('预览标记含密钥', importModalText.includes('含密钥'))

  // 关闭「导入后自动测试」（避免真实下载 npx 包）
  await page.locator('.mcp-import__options .ant-switch').first().click()
  await page.waitForTimeout(300)
  await page.click('.ant-modal-footer .ant-btn-primary')
  await page.waitForTimeout(3000)

  const resultText = (await page.textContent('.ant-modal-content')) || ''
  check('导入结果展示新增与工具状态', resultText.includes('新增') && resultText.includes(IMPORT_KEY),
    resultText.replace(/\s+/g, ' ').slice(0, 100))
  await page.click('.ant-modal-footer button:not(.ant-btn-primary)')
  await page.waitForTimeout(1200)
  const listAfterImport = (await page.textContent('.page-container')) || ''
  check('导入的服务出现在列表', listAfterImport.includes(IMPORT_KEY))

  console.log('[6.1] 导出配置')
  await page.click('button:has-text("导出配置")')
  await page.waitForSelector('.mcp-export__content', { timeout: 8000 })
  await page.waitForTimeout(1500)
  const exportText = (await page.textContent('.mcp-export__content')) || ''
  check('导出为 mcpServers 格式', exportText.includes('mcpServers'))
  check('导出默认脱敏密钥',
    exportText.includes('AMAP_MAPS_API_KEY') && !exportText.includes('您在高德官网上申请的key'),
    exportText.includes('您在高德官网上申请的key') ? '出现明文密钥' : '密钥已脱敏')
  await page.keyboard.press('Escape')
  await page.waitForTimeout(500)

  /* ------------------------------------------------------------ 清理 */
  console.log('[7] 清理测试数据')
  if (token) {
    const listRes = await fetch(`${API_BASE}/mcp/servers?page_size=100`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const list = await listRes.json()
    for (const item of list.data?.items || []) {
      if (item.name.startsWith('E2E')) {
        await fetch(`${API_BASE}/mcp/servers/${item.id}`, {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${token}` },
        })
        console.log(`  已清理测试 MCP 服务：${item.name}`)
      }
    }
  }

  const serious = consoleErrors.filter(
    (text) => !text.includes('favicon') && !text.includes('Download the Vue Devtools'),
  )
  check('无严重控制台错误', serious.length === 0, serious.slice(0, 2).join(' | '))

  console.log('\n' + '='.repeat(66))
  console.log(`MCP E2E 结果：通过 ${passed} 项，失败 ${failed} 项`)
  console.log('='.repeat(66))
} catch (error) {
  failed += 1
  console.error('\n[MCP E2E 异常]', error.message)
  await page.screenshot({ path: 'e2e-mcp-failure.png', fullPage: true }).catch(() => undefined)
} finally {
  await browser.close()
}

process.exit(failed === 0 ? 0 : 1)
