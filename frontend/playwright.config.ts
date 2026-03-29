import { defineConfig, devices } from "@playwright/test";

const isCI = Boolean(process.env.CI);
const E2E_BACKEND_PORT = 8100;
const E2E_FRONTEND_PORT = 3100;

export default defineConfig({
  testDir: "./e2e",
  timeout: 120_000,
  expect: {
    timeout: 10_000,
  },
  fullyParallel: false,
  retries: isCI ? 1 : 0,
  workers: 1,
  reporter: isCI ? [["github"], ["html", { open: "never" }]] : [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${E2E_FRONTEND_PORT}`,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: [
    {
      command:
        `bash -lc 'mkdir -p .tmp && rm -f .tmp/e2e-projects.json && ONEFILE_PROJECTS_FILE=.tmp/e2e-projects.json ONEFILE_AUTH_DEBUG_CODES=1 python3 -m uvicorn backend.main:app --host 127.0.0.1 --port ${E2E_BACKEND_PORT}'`,
      url: `http://127.0.0.1:${E2E_BACKEND_PORT}/health`,
      cwd: "..",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `npm run dev -- --port ${E2E_FRONTEND_PORT}`,
      url: `http://127.0.0.1:${E2E_FRONTEND_PORT}`,
      cwd: ".",
      env: {
        BACKEND_API_URL: `http://127.0.0.1:${E2E_BACKEND_PORT}`,
      },
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
