import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e/integration',
  timeout: 60000,
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  globalSetup: './e2e/integration-setup.ts',
  globalTeardown: './e2e/integration-teardown.ts',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
  },
  projects: [
    {
      name: 'integration',
      testDir: './e2e/integration',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    env: {
      NEXT_PUBLIC_FIREBASE_API_KEY: 'fake-api-key',
      NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN: 'localhost',
      NEXT_PUBLIC_FIREBASE_PROJECT_ID: 'chat-vote-dev',
      NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET: 'chat-vote-dev.appspot.com',
      NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID: '000000000000',
      NEXT_PUBLIC_FIREBASE_APP_ID: '1:000000000000:web:fake',
      NEXT_PUBLIC_USE_FIREBASE_EMULATORS: 'true',
      NEXT_PUBLIC_API_URL: 'http://localhost:8080',
      NEXT_PUBLIC_APP_URL: 'http://localhost:3000',
      FIRESTORE_EMULATOR_HOST: 'localhost:8081',
      FIREBASE_AUTH_EMULATOR_HOST: 'localhost:9099',
    },
  },
});
