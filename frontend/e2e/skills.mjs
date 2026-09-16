/**
 * 技能（Skills）端到端测试（Playwright）
 *
 * 覆盖完整闭环：
 *   技能管理页（内置技能 / 动态配置表单 / 试运行 / 新建自定义 HTTP 技能 / 删除）
 *   → 聊天页勾选技能 → 模型触发 tool calling → 展示技能调用记录 → 会话级技能记忆
 *
 * 运行前请先启动后端与前端，然后：node e2e/skills.mjs
 */
import { chromium } from 'playwright'

const BASE = process.env.E2E_BASE_URL || 'http://127.0.0.1:5173'
const API_BASE = process.env.E2E_API_URL || 'http://127.0.0.1:8000/api'
const USERNAME = process.env.E2E_USERNAME || 'admin'
const PASSWORD = process.env.E2E_PASSWORD || 'admin123456'
const SKILL_NAME = `E2E 接口技能 ${Date.now().toString().slice(-5)}`

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

/** 让对话固定使用内置 mock 模型（避免消耗真实模型额度，并保证 tool calling 可复现） */
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
    localStorage.setItem('ai_chat_settings', JSON.stringify(state))
  }, mock.id)
  return mock
}

const browser = await chromium.launch({ channel: 'msedge', headless: true })
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN' })
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

  /* ------------------------------------------------------------ 技能管理页 */
  console.log('[2] 技能管理页')
  await page.goto(`${BASE}/admin/skills`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1200)
  const listText = (await page.textContent('.page-container')) || ''
  check('展示内置技能', listText.includes('计算器') && listText.includes('当前时间'), '')
  check('展示联网搜索与网页抓取', listText.includes('联网搜索') && listText.includes('网页抓取'))
  check('技能列表显示配置状态', /已配置|待配置/.test(listText))
  const rowCount = await page.locator('.ant-table-tbody tr.ant-table-row').count()
  check('技能表格有数据', rowCount >= 4, `${rowCount} 行`)

  /* ------------------------------------------------------------ 试运行 */
  console.log('\n[3] 试运行技能（当前表单配置，无需保存）')
  const calcRow = page.locator('.ant-table-tbody tr.ant-table-row', { hasText: '计算器' }).first()
  // 注意：行里的「启用开关」也是 button，必须定位到「操作列」里的按钮
  await calcRow.locator('td').last().locator('button').first().click()
  await page.waitForSelector('.ant-drawer-open', { timeout: 8000 })
  await page.waitForTimeout(800)
  const drawerText = (await page.textContent('.ant-drawer-open')) || ''
  check('配置抽屉展示动态表单', drawerText.includes('技能配置') && drawerText.includes('结果小数位'))
  check('抽屉包含试运行区', drawerText.includes('试运行'))

  const argInput = page.locator('.ant-drawer-open .ant-form-item').filter({ hasText: 'expression' }).locator('input')
  await argInput.fill('(88+12)/4*3')
  await page.click('.ant-drawer-open button:has-text("试运行")')
  await page.waitForTimeout(2500)
  const resultText = (await page.textContent('.ant-drawer-open .skill-form__result')) || ''
  check('试运行返回结果', resultText.includes('75'), resultText.replace(/\s+/g, ' ').slice(0, 90))
  await page.keyboard.press('Escape')
  await page.waitForTimeout(500)

  /* ------------------------------------------------------------ 新建自定义 HTTP 技能 */
  console.log('\n[4] 新建自定义 HTTP 技能')
  await page.click('button:has-text("新建技能")')
  await page.waitForSelector('.ant-drawer-open', { timeout: 8000 })
  await page.waitForTimeout(600)
  await page.click('.skill-type:has-text("自定义 HTTP 接口")')
  await page.waitForTimeout(400)
  await page.fill('.ant-drawer-open input[placeholder="例如：订单查询接口"]', SKILL_NAME)
  await page.fill('.ant-drawer-open textarea', '查询订单状态。当用户询问订单进度时使用。')
  // URL / 入参定义
  const urlInput = page.locator('.ant-drawer-open .ant-form-item').filter({ hasText: '接口地址' }).locator('input')
  await urlInput.fill('http://127.0.0.1:9/orders')
  const schemaArea = page
    .locator('.ant-drawer-open .ant-form-item')
    .filter({ hasText: '入参定义' })
    .locator('textarea')
  await schemaArea.fill('{\n  "order_id": {"type": "string", "description": "订单号"}\n}')
  // 试运行（连接失败也应给出可读错误）
  const draftArg = page.locator('.ant-drawer-open .ant-form-item').filter({ hasText: 'order_id' }).locator('input')
  if (await draftArg.count()) await draftArg.fill('A1001')
  await page.click('.ant-drawer-open button:has-text("试运行")')
  await page.waitForTimeout(3000)
  const draftResult = (await page.textContent('.ant-drawer-open .skill-form__result')) || ''
  check('自定义技能可试运行并返回可读错误', draftResult.length > 0, draftResult.replace(/\s+/g, ' ').slice(0, 80))

  // 注意：Ant Design 会在两个汉字的按钮里插空格（保 存），所以按样式定位主按钮
  await page.locator('.ant-drawer-open .ant-btn-primary').last().click()
  await page.waitForTimeout(1800)
  const afterCreate = (await page.textContent('.page-container')) || ''
  check('自定义技能创建成功', afterCreate.includes(SKILL_NAME))

  /* ------------------------------------------------------------ 聊天中使用技能 */
  console.log('\n[5] 聊天中调用技能（tool calling）')
  await page.goto(`${BASE}/chat`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1200)
  await page.click('.chat-input .tool-btn:has(.anticon-thunderbolt)')
  await page.waitForTimeout(800)
  const panelText = (await page.textContent('.skill-selector__panel')) || ''
  check('技能选择器展示可用技能', panelText.includes('计算器') && panelText.includes('当前时间'))

  // 用接口真实数据校验「聊天可选范围」：仅 enabled + visible_to_users 且已完成配置的技能
  const skillToken = await page.evaluate(() => localStorage.getItem('ai_chat_token'))
  const allSkills = await fetch(`${API_BASE}/skills?page_size=100`, {
    headers: { Authorization: `Bearer ${skillToken}` },
  }).then((r) => r.json())
  const disabledSkills = (allSkills.data?.items || []).filter(
    (item) => !item.enabled || !item.visible_to_users,
  )
  const leaked = disabledSkills.filter((item) => panelText.includes(item.name))
  check(
    '已禁用 / 不可见的技能不出现在选择器',
    leaked.length === 0,
    disabledSkills.length ? `已禁用/不可见：${disabledSkills.map((i) => i.name).join('、')}` : '（当前没有禁用技能）',
  )
  await page.click('.skill-selector__item:has-text("计算器") .ant-checkbox-input')
  await page.waitForTimeout(400)
  await page.keyboard.press('Escape')
  await page.waitForTimeout(400)
  const badge = await page.locator('.tool-btn__badge').first().textContent()
  check('已选技能数量提示', badge?.trim() === '1', `badge=${badge}`)

  await page.fill('textarea', '帮我计算 (88+12)/4*3 等于多少')
  await page.keyboard.press('Enter')
  await page.waitForSelector('.chat-message.is-assistant .markdown-body', { timeout: 30000 })
  await page.waitForSelector('.skill-call', { timeout: 30000 })
  const callText = (await page.textContent('.skill-call')) || ''
  check('回答下方展示技能调用记录', callText.includes('已调用技能'))

  await page.click('.skill-call__head')
  await page.waitForTimeout(500)
  const callDetail = (await page.textContent('.skill-call')) || ''
  check('展开后可见入参与结果', callDetail.includes('expression') && callDetail.includes('75'),
    callDetail.replace(/\s+/g, ' ').slice(0, 100))

  const answer = (await page.textContent('.chat-message.is-assistant .markdown-body')) || ''
  check('最终回答引用了技能结果', answer.includes('75'), answer.replace(/\s+/g, ' ').slice(0, 80))

  /* ------------------------------------------------------------ 会话级技能记忆 */
  console.log('\n[6] 会话级技能记忆')
  await page.reload({ waitUntil: 'networkidle' })
  await page.waitForTimeout(1500)
  const badgeAfterReload = await page.locator('.tool-btn__badge').first().textContent()
  check('刷新后仍保留会话选中的技能', badgeAfterReload?.trim() === '1', `badge=${badgeAfterReload}`)

  const token = await page.evaluate(() => localStorage.getItem('ai_chat_token'))
  const convRes = await fetch(`${API_BASE}/conversations?page_size=1`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const convBody = await convRes.json()
  const latest = convBody.data?.items?.[0]
  check('会话已持久化 skill_ids', Array.isArray(latest?.skill_ids) && latest.skill_ids.length > 0,
    JSON.stringify(latest?.skill_ids))

  /* ------------------------------------------------------------ 清理 */
  console.log('\n[7] 清理测试数据')
  if (token) {
    const listRes = await fetch(`${API_BASE}/skills?page_size=100`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const list = await listRes.json()
    for (const item of list.data?.items || []) {
      if (item.name.startsWith('E2E 接口技能')) {
        await fetch(`${API_BASE}/skills/${item.id}`, {
          method: 'DELETE',
          headers: { Authorization: `Bearer ${token}` },
        })
        console.log(`  已清理测试技能：${item.name}`)
      }
    }
  }

  const serious = consoleErrors.filter(
    (text) => !text.includes('favicon') && !text.includes('Download the Vue Devtools'),
  )
  check('无严重控制台错误', serious.length === 0, serious.slice(0, 2).join(' | '))

  console.log('\n' + '='.repeat(66))
  console.log(`技能 E2E 结果：通过 ${passed} 项，失败 ${failed} 项`)
  console.log('='.repeat(66))
} catch (error) {
  failed += 1
  console.error('\n[技能 E2E 异常]', error.message)
  await page.screenshot({ path: 'e2e-skills-failure.png', fullPage: true }).catch(() => undefined)
} finally {
  await browser.close()
}

process.exit(failed === 0 ? 0 : 1)
