import { defineConfig, devices } from '@playwright/test'
import path from 'node:path'
import { fileURLToPath } from 'node:url'


const configDir = path.dirname(fileURLToPath(import.meta.url))
const projectRoot = path.resolve(configDir, '..')
const backendRoot = path.join(projectRoot, 'backend')
const backendCommand = process.platform === 'win32'
  ? '.venv\\Scripts\\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000'
  : '.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000'
const frontendCommand = process.platform === 'win32'
  ? 'npm.cmd run dev -- --host 127.0.0.1'
  : 'npm run dev -- --host 127.0.0.1'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  outputDir: path.join(projectRoot, 'output', 'playwright', 'test-results'),
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      command: backendCommand,
      cwd: backendRoot,
      env: { ...process.env, LLM_API_KEY: '' },
      url: 'http://127.0.0.1:8000/api/health',
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: frontendCommand,
      cwd: path.join(projectRoot, 'frontend'),
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
})
