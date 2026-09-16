/**
 * 侧边栏折叠 / 展开按钮的几何断言（Playwright）
 *
 * 背景：折叠态侧边栏只有 64px 宽，早期实现里 logo(30) + gap(8) + 按钮(28) + padding(24) = 90px，
 * 按钮被挤出容器、被右侧聊天区盖住（用户反馈「展开侧边栏按钮被遮挡」）。
 *
 * 本脚本用「包围盒 + 命中测试」验证修复效果，而不是靠肉眼：
 *   1. 展开态：logo 与「收起」按钮都可见，且都在侧边栏内；
 *   2. 折叠态：「展开」按钮完全位于侧边栏矩形内；
 *   3. 按钮中心点 elementFromPoint 命中按钮自身或其图标（说明没被其他元素遮挡）；
 *   4. 点击能重新展开（宽度回到 272）；
 *   5. 折叠态下侧边栏无横向溢出（scrollWidth <= clientWidth）。
 *
 * 运行：node e2e/sidebar.mjs（需后端 :8000 与前端 :5173 已启动）
 */
import { chromium } from 'playwright'

const BASE = process.env.E2E_BASE_URL || 'http://127.0.0.1:5173'
const USERNAME = process.env.E2E_USERNAME || 'admin'
const PASSWORD = process.env.E2E_PASSWORD || 'admin123456'

let passed = 0
let failed = 0

function check(name, condition, detail = '') {
  if (condition) {
    passed += 1
    console.log(`  [PASS] ${name} ${detail}`)
  } else {
    failed += 1
    console.log(`  [FAIL] ${name} ${detail}`)
  }
}

const browser = await chromium.launch({ channel: 'msedge', headless: true })

async function measure(page) {
  return page.evaluate(() => {
    const sider = document.querySelector('.chat-layout__sider')
    const brand = document.querySelector('.chat-layout__brand')
    const button = document.querySelector('.chat-layout__collapse')
    const logo = document.querySelector('.chat-layout__brand .app-logo')
    if (!sider || !button) return null
    const s = sider.getBoundingClientRect()
    const b = button.getBoundingClientRect()
    const brandRect = brand?.getBoundingClientRect()
    const cx = b.left + b.width / 2
    const cy = b.top + b.height / 2
    const hit = document.elementFromPoint(cx, cy)
    const icon = button.querySelector('.anticon')
    const iconRect = icon?.getBoundingClientRect()
    return {
      siderWidth: Math.round(s.width),
      siderBox: { left: s.left, right: s.right, width: s.width },
      buttonBox: { left: b.left, right: b.right, width: b.width, height: b.height },
      brandBox: brandRect ? { left: brandRect.left, right: brandRect.right, width: brandRect.width } : null,
      logoVisible: Boolean(logo && logo.getBoundingClientRect().width > 0),
      insideSider: b.left >= s.left - 0.5 && b.right <= s.right + 0.5,
      overflowRight: Math.round(b.right - s.right),
      hitIsButton: hit === button || button.contains(hit),
      hitDesc: hit ? `${hit.tagName.toLowerCase()}.${(hit.className || '').toString().split(' ')[0]}` : 'null',
      scrollWidth: sider.scrollWidth,
      clientWidth: sider.clientWidth,
      buttonIcon: Boolean(iconRect && iconRect.width > 0),
    }
  })
}

try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: 'zh-CN' })
  const page = await context.newPage()

  // 登录
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle' })
  await page.fill('input[autocomplete="username"]', USERNAME)
  await page.fill('input[autocomplete="current-password"]', PASSWORD)
  await page.click('button[type="submit"]')
  await page.waitForURL('**/chat', { timeout: 15000 })
  await page.waitForSelector('.chat-layout__sider', { timeout: 10000 })
  await page.waitForTimeout(600)

  for (const width of [1680, 1440, 1280, 1100, 1024]) {
    console.log(`\n[视口 ${width}px]`)
    await page.setViewportSize({ width, height: 900 })
    await page.waitForTimeout(400)

    // 确保是展开态
    let m = await measure(page)
    if (m.siderWidth < 200) {
      await page.click('.chat-layout__collapse')
      await page.waitForTimeout(500)
      m = await measure(page)
    }

    check('展开态：侧边栏宽 272', m.siderWidth === 272, `${m.siderWidth}px`)
    check('展开态：logo 可见', m.logoVisible)
    check('展开态：收起按钮在侧边栏内', m.insideSider, `右侧超出 ${m.overflowRight}px`)
    check('展开态：按钮图标可见', m.buttonIcon)
    check('展开态：按钮可被点击（未被遮挡）', m.hitIsButton, `命中 ${m.hitDesc}`)

    // 折叠
    await page.click('.chat-layout__collapse')
    await page.waitForTimeout(600)
    const c = await measure(page)

    check('折叠态：侧边栏宽 64', c.siderWidth === 64, `${c.siderWidth}px`)
    check('折叠态：logo 已隐藏', !c.logoVisible)
    check('折叠态：按钮尺寸 >= 32×32（可点击面积足够）', c.buttonBox.width >= 32 && c.buttonBox.height >= 32,
      `${Math.round(c.buttonBox.width)}×${Math.round(c.buttonBox.height)}`)
    check('折叠态：按钮完全位于侧边栏内（不再被挤出）', c.insideSider, `右侧超出 ${c.overflowRight}px`)
    check('折叠态：按钮未被聊天区遮挡（命中测试）', c.hitIsButton, `命中 ${c.hitDesc}`)
    check('折叠态：按钮水平居中', Math.abs((c.buttonBox.left + c.buttonBox.right) / 2 - (c.siderBox.left + c.siderBox.right) / 2) <= 1.5,
      `偏差 ${(Math.abs((c.buttonBox.left + c.buttonBox.right) / 2 - (c.siderBox.left + c.siderBox.right) / 2)).toFixed(2)}px`)
    check('折叠态：侧边栏无横向溢出', c.scrollWidth <= c.clientWidth + 1, `scrollWidth=${c.scrollWidth} clientWidth=${c.clientWidth}`)

    // 点击重新展开
    await page.click('.chat-layout__collapse')
    await page.waitForTimeout(500)
    const reopened = await measure(page)
    check('点击可重新展开', reopened.siderWidth === 272 && reopened.logoVisible, `${reopened.siderWidth}px`)

    // 桌面端顶部导航的菜单按钮也应能折叠 / 展开侧边栏
    await page.click('.chat-header__left .chat-header__icon-btn')
    await page.waitForTimeout(500)
    const viaHeader = await measure(page)
    check('桌面端：顶部菜单按钮可折叠侧边栏', viaHeader.siderWidth === 64, `${viaHeader.siderWidth}px`)
    await page.click('.chat-header__left .chat-header__icon-btn')
    await page.waitForTimeout(500)
    const viaHeaderBack = await measure(page)
    check('桌面端：再次点击可恢复展开', viaHeaderBack.siderWidth === 272 && viaHeaderBack.logoVisible, `${viaHeaderBack.siderWidth}px`)

    if (width === 1280) {
      await page.click('.chat-layout__collapse')
      await page.waitForTimeout(500)
      await page.screenshot({ path: 'e2e-sidebar-collapsed.png', clip: { x: 0, y: 0, width: 260, height: 420 } })
      await page.click('.chat-layout__collapse')
      await page.waitForTimeout(400)
    }
  }

  /* ------------------------------------------------------------ 管理后台侧边栏 */
  console.log('\n[管理后台侧边栏]')
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto(`${BASE}/admin/models`, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1200)

  const adminSider = page.locator('.admin-layout__sider')
  const adminLogo = page.locator('.admin-layout__brand .app-logo')
  let adminBox = await adminSider.boundingBox()
  let logoBox = await adminLogo.boundingBox()
  check('后台：侧边栏展开宽 216', Math.round(adminBox.width) === 216, `${Math.round(adminBox.width)}px`)
  check('后台：logo 完整位于侧边栏内', logoBox.x >= adminBox.x - 0.5 && logoBox.x + logoBox.width <= adminBox.x + adminBox.width + 0.5)

  await page.click('.admin-layout__icon-btn')
  await page.waitForTimeout(700)
  adminBox = await adminSider.boundingBox()
  logoBox = await adminLogo.boundingBox()
  check('后台：可折叠', Math.round(adminBox.width) < 216, `${Math.round(adminBox.width)}px`)
  check('后台：折叠态 logo 未溢出侧边栏', logoBox.x + logoBox.width <= adminBox.x + adminBox.width + 0.5,
    `logo 右边=${Math.round(logoBox.x + logoBox.width)} 侧边栏右边=${Math.round(adminBox.x + adminBox.width)}`)

  await page.click('.admin-layout__icon-btn')
  await page.waitForTimeout(600)
  adminBox = await adminSider.boundingBox()
  check('后台：可恢复展开', Math.round(adminBox.width) === 216, `${Math.round(adminBox.width)}px`)

  /* ------------------------------------------------------------ 窄屏（移动端） */
  let narrowPass = 0
  for (const [w, h] of [[418, 900], [390, 844]]) {
    console.log(`\n[窄屏 ${w}${h}]`)
    await page.setViewportSize({ width: w, height: h })
    await page.goto(`${BASE}/chat`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(1200)

    const rail = await page.locator('.chat-layout__sider').count()
    check('窄屏：侧边栏改为抽屉（无固定栏）', rail === 0)

    // 顶部导航里的「展开会话列表」按钮（此前是空实现）
    const headerBtn = page.locator('.chat-header__left .chat-header__icon-btn').first()
    const headerBox = await headerBtn.boundingBox()
    check('窄屏：顶部展开按钮可见', Boolean(headerBox), headerBox ? `${Math.round(headerBox.width)}${Math.round(headerBox.height)}` : '未找到')
    const headerHit = await page.evaluate(([x, y]) => {
      const el = document.elementFromPoint(x, y)
      return Boolean(el && el.closest('.chat-header__left'))
    }, [headerBox.x + headerBox.width / 2, headerBox.y + headerBox.height / 2])
    check('窄屏：顶部展开按钮未被遮挡（命中测试）', headerHit)

    await headerBtn.click()
    await page.waitForSelector('.ant-drawer-open', { timeout: 8000 })
    await page.waitForTimeout(600)
    const listVisible = await page.locator('.ant-drawer-open .conversation-list').count()
    check('窄屏：顶部按钮可打开会话抽屉并显示列表', listVisible > 0)

    await page.click('.ant-drawer-open .chat-layout__collapse')
    await page.waitForTimeout(700)
    check('窄屏：抽屉关闭按钮可用', (await page.locator('.ant-drawer-open').count()) === 0)

    // 浮动「新建聊天」按钮不与输入区重叠
    const fabLocator = page.locator('.chat-layout__fab')
    const fab = await fabLocator.boundingBox()
    const inputBox = await page.locator('.chat-page__input').boundingBox()
    check('窄屏：浮动新建按钮可见', Boolean(fab))
    check(
      '窄屏：浮动按钮不与输入区重叠',
      Boolean(fab && inputBox) && fab.y + fab.height <= inputBox.y + 1,
      fab && inputBox ? `按钮底部=${Math.round(fab.y + fab.height)} 输入区顶部=${Math.round(inputBox.y)}` : '',
    )
    if (fab) {
      const fabHit = await page.evaluate(([x, y]) => {
        const el = document.elementFromPoint(x, y)
        return Boolean(el && el.closest('.chat-layout__fab'))
      }, [fab.x + fab.width / 2, fab.y + fab.height / 2])
      check('窄屏：浮动按钮未被遮挡（命中测试）', fabHit)
      await fabLocator.click()
      await page.waitForTimeout(800)
      check('窄屏：浮动按钮可新建会话', (await page.locator('.chat-input textarea').count()) > 0)
    }

    await page.screenshot({ path: `e2e-mobile-${w}.png` })
    narrowPass += 1
  }

  console.log('\n' + '='.repeat(66))
  console.log(`侧边栏 / 抽屉检查：通过 ${passed} 项，失败 ${failed} 项`)
  console.log('='.repeat(66))
} catch (error) {
  failed += 1
  console.error('\n[检查异常]', error.message)
} finally {
  await browser.close()
}

process.exit(failed === 0 ? 0 : 1)
