import { expect, test } from '@playwright/test'

/**
 * 输入校验与模式错误分支（补充主线之外的失败路径）。
 * 注意：这些用例依赖后端未配置 OPENAI_API_KEY（Demo 环境）。
 */
test('非法上传：扩展名与体积在前端被拦截', async ({ page }) => {
  await page.goto('/')

  const fileInput = page.locator('input[type=file]')
  await fileInput.setInputFiles({
    name: 'notes.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('a,b\n1,2\n'),
  })
  await expect(page.getByText(/不支持的文件类型/)).toBeVisible()

  const big = Buffer.alloc(26 * 1024 * 1024, 97)
  await fileInput.setInputFiles({ name: 'big.csv', mimeType: 'text/csv', buffer: big })
  await expect(page.getByText(/超过 25 MB 限制/)).toBeVisible()

  await page.screenshot({ path: 'test-results/e2e-invalid-upload.png' })
})

test('选择 Live 但未配置 Key：给出解释并可一键改用 Demo', async ({ page }) => {
  await page.goto('/')

  const sample = page.getByRole('button', { name: '销售订单示例数据', exact: true })
  if (await sample.count()) {
    await sample.first().click()
    await expect(page.getByText(/7,180 行/).first()).toBeVisible()
  }

  await page.getByRole('radio', { name: /^Live：/ }).click()

  // 选 Live 时就应该提示（来自 /api/config 的 llm_mode），不用等提交
  await expect(page.getByText(/当前后端未配置 API Key/)).toBeVisible({ timeout: 10_000 })
  await page.screenshot({ path: 'test-results/e2e-live-selected.png' })

  await page.getByLabel('分析问题').fill('各渠道收入有什么差异？')
  await page.getByRole('button', { name: '开始分析' }).click()

  await expect(page.getByRole('alert').filter({ hasText: '未配置大模型 API Key' })).toBeVisible({
    timeout: 20_000,
  })
  await page.screenshot({ path: 'test-results/e2e-live-blocked.png' })

  await page.getByRole('button', { name: '改用 Demo 重试' }).click()
  await page.waitForURL(/\/workspace\/run_/, { timeout: 30_000 })
  await expect(page.getByRole('heading', { name: '分析计划' })).toBeVisible()
})
