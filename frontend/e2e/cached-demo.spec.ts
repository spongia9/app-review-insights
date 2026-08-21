import { expect, test, type Page } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'


const testDir = path.dirname(fileURLToPath(import.meta.url))
const screenshotRoot = path.resolve(testDir, '..', '..', 'output', 'playwright', 'phase7')

async function openCachedDemo(page: Page) {
  const consoleErrors: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  await page.goto('/')
  await expect(page.getByText('后端已连接')).toBeVisible()
  await expect(page.getByRole('heading', { name: '新建分析' })).toBeVisible()
  await page.getByTestId('view-cached-demo').click()
  await expect(page.getByTestId('cached-demo-banner')).toContainText('示例缓存结果')
  await expect(page.getByTestId('workspace-overview')).toBeVisible()
  return consoleErrors
}

test('cached demo is complete, bilingual, persistent, and no-key safe', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  const consoleErrors = await openCachedDemo(page)

  const coreTabs = ['overview', 'findings', 'requirements', 'prd', 'traceability'] as const
  for (const tab of coreTabs) {
    await page.getByTestId(`workspace-tab-${tab}`).click()
    await expect(page.getByTestId(`workspace-${tab}`)).toBeVisible()
    await page.screenshot({
      path: path.join(screenshotRoot, `phase7-1440x900-${tab}.png`),
      fullPage: true,
    })
  }

  await page.getByTestId('language-switcher').selectOption('en-US')
  await expect(page.getByTestId('cached-demo-banner')).toContainText('Cached Demo Result')
  await page.reload()
  await expect(page.getByRole('heading', { name: 'New Analysis' })).toBeVisible()
  await expect(page.getByTestId('cached-demo-banner')).toContainText('Cached Demo Result')
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  expect(consoleErrors).toEqual([])
})

test('live analysis without an API key fails clearly without fake results', async ({ page }) => {
  const consoleErrors: string[] = []
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text())
  })
  await page.goto('/')
  await page.getByTestId('source-json').click()
  await page.getByTestId('review-file').setInputFiles(
    path.resolve(testDir, '..', '..', 'sample_data', 'workout_compatible_sample.json'),
  )
  await page.getByTestId('start-analysis').click()
  await expect(page.getByTestId('analysis-workspace')).toBeVisible()
  await expect(page.getByRole('alert')).toContainText('实时分析尚未配置', { timeout: 15_000 })
  await page.getByTestId('workspace-tab-topics').click()
  await expect(page.getByTestId('workspace-topics')).toContainText('该阶段结果将在流水线完成后显示')
  await page.screenshot({
    path: path.join(screenshotRoot, 'phase7-no-key-failure.png'),
    fullPage: true,
  })
  expect(consoleErrors).toEqual([])
})

for (const viewport of [
  { width: 1366, height: 768 },
  { width: 1920, height: 1080 },
  { width: 390, height: 844 },
]) {
  test(`cached workspace is responsive at ${viewport.width}x${viewport.height}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    const consoleErrors = await openCachedDemo(page)
    await page.getByTestId('workspace-tab-traceability').click()
    await expect(page.getByTestId('workspace-traceability')).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    await page.screenshot({
      path: path.join(screenshotRoot, `phase7-${viewport.width}x${viewport.height}-traceability.png`),
      fullPage: true,
    })
    expect(consoleErrors).toEqual([])
  })
}
