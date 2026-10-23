import { defineConfig, devices } from '@playwright/test'

/**
 * E2E 前置条件（不在配置里自动拉起服务，避免把 Python 后端也塞进 webServer）：
 *   终端 1：cd backend && .\.venv\Scripts\python -m uvicorn app.main:app --port 8000
 *   终端 2：cd frontend && pnpm dev
 * 然后：pnpm e2e
 */
export default defineConfig({
  testDir: './tests/e2e',
  timeout: 180_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173',
    viewport: { width: 1440, height: 900 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    acceptDownloads: true,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
