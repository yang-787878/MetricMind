import { expect, test } from '@playwright/test'

/**
 * 主线 E2E（§10.1 最后一条）：
 * 首页 → 载入示例数据 → 提问 → 计划与工具调用 → 图表 → 报告页 → 导出 HTML 下载成功。
 */
test('demo 主线：示例数据 → 提问 → 计划/工具/图表 → 报告 → 导出', async ({ page }) => {
  await page.goto('/')

  // 1. 载入示例数据（若已载入则跳过）
  const sampleChip = page.getByRole('button', { name: '销售订单示例数据', exact: true })
  if (await sampleChip.count()) {
    await sampleChip.first().click()
    await expect(page.getByText(/7,180 行/).first()).toBeVisible()
  }

  // 2. 提问并提交
  const input = page.getByLabel('分析问题')
  await input.fill('为什么 2025 年 9 月销售额相比 6-8 月下降了？')
  await page.getByRole('button', { name: '开始分析' }).click()

  // 3. 进入工作区
  await page.waitForURL(/\/workspace\/run_/, { timeout: 30_000 })
  await expect(page.getByRole('heading', { name: '分析计划' })).toBeVisible()

  // 4. 计划里至少 2 个工具与步骤标题
  await expect(page.getByText('calculate_metrics').first()).toBeVisible({ timeout: 60_000 })
  const toolChips = page.getByText('calculate_metrics')
  await expect(toolChips.first()).toBeVisible()

  // 5. 运行结束
  await expect(page.locator('header').getByText(/成功|部分结果/).first()).toBeVisible({ timeout: 180_000 })

  // 6. 至少一张图表（Recharts SVG）
  await expect(page.locator('svg.recharts-surface').first()).toBeVisible()

  // 7. 打开完整报告
  await page.getByRole('link', { name: /打开完整报告/ }).click()
  await page.waitForURL(/\/runs\/run_[^/]+\/report/)
  await expect(page.getByRole('heading', { name: '数字核验' })).toBeVisible()
  await expect(page.getByText(/所有数值来自工具执行结果/).first()).toBeVisible()

  // 8. 导出 HTML 并验证真实下载
  const [download] = await Promise.all([
    page.waitForEvent('download', { timeout: 60_000 }),
    (async () => {
      await page.locator('article').getByRole('button', { name: /^导出/ }).click()
      await page.getByRole('menuitem', { name: /HTML 报告/ }).click()
    })(),
  ])
  const filename = download.suggestedFilename()
  expect(filename.endsWith('.html')).toBe(true)
  const path = await download.path()
  expect(path).toBeTruthy()

  // 9. 截图留档（失败时也可用 playwright-report）
  await page.screenshot({ path: 'test-results/e2e-report.png', fullPage: true })
})
