import { defineConfig, devices } from "@playwright/test";

import { getOrAllocatePorts } from "./e2e/support/port-utils";

const ports = getOrAllocatePorts();

export default defineConfig({
  testDir: "./e2e/mock",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 1,
  workers: process.env.CI ? 2 : 2,
  reporter: "html",
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  timeout: 60000,
  use: {
    baseURL: `http://localhost:${ports.frontend}`,
    trace: "on-first-retry",
    navigationTimeout: 45000,
  },
  projects: [
    {
      name: "mock",
      testDir: "./e2e/mock",
      testIgnore: [
        "**/streamed-responses.spec.ts",
        "**/quick-replies.spec.ts",
        "**/quick-replies-extended.spec.ts",
        "**/source-attribution.spec.ts",
        "**/source-attribution-extended.spec.ts",
        "**/feedback.spec.ts",
        "**/pro-con.spec.ts",
        "**/persisted-sessions.spec.ts",
        "**/persisted-sessions-extended.spec.ts",
        "**/reset-emulator.setup.ts",
        "**/demographics.spec.ts",
      ],
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "emulator-reset",
      testDir: "./e2e/mock",
      testMatch: "**/reset-emulator.setup.ts",
      dependencies: ["mock"],
    },
    {
      name: "mock-serial",
      testDir: "./e2e/mock",
      testMatch: [
        "**/streamed-responses.spec.ts",
        "**/quick-replies.spec.ts",
        "**/quick-replies-extended.spec.ts",
        "**/source-attribution.spec.ts",
        "**/source-attribution-extended.spec.ts",
        "**/feedback.spec.ts",
        "**/pro-con.spec.ts",
        "**/persisted-sessions.spec.ts",
        "**/persisted-sessions-extended.spec.ts",
        "**/demographics.spec.ts",
      ],
      fullyParallel: false,
      use: { ...devices["Desktop Chrome"] },
      dependencies: ["emulator-reset"],
    },
  ],
  webServer: {
    // Dynamic port avoids conflicts with dev servers on :3000/:3001.
    // The mock Socket.IO server port is also dynamic (see global-setup.ts).
    // CI uses a production build (fast startup); local dev uses Turbopack HMR.
    command: process.env.CI
      ? `npm run build && PORT=${ports.frontend} npm run start`
      : `PORT=${ports.frontend} npm run dev`,
    url: `http://localhost:${ports.frontend}`,
    reuseExistingServer: !process.env.CI,
    timeout: process.env.CI ? 180000 : 120000,
    env: {
      NEXT_PUBLIC_FIREBASE_API_KEY: "fake-api-key",
      NEXT_PUBLIC_FIREBASE_AUTH_DOMAIN: "localhost",
      NEXT_PUBLIC_FIREBASE_PROJECT_ID: "chat-vote-dev",
      NEXT_PUBLIC_FIREBASE_STORAGE_BUCKET: "chat-vote-dev.appspot.com",
      NEXT_PUBLIC_FIREBASE_MESSAGING_SENDER_ID: "000000000000",
      NEXT_PUBLIC_FIREBASE_APP_ID: "1:000000000000:web:fake",
      NEXT_PUBLIC_USE_FIREBASE_EMULATORS: "true",
      NEXT_PUBLIC_API_URL: `http://localhost:${ports.mockSocket}`,
      NEXT_PUBLIC_APP_URL: `http://localhost:${ports.frontend}`,
      FIRESTORE_EMULATOR_HOST: "localhost:8081",
      FIREBASE_AUTH_EMULATOR_HOST: "localhost:9099",
    },
  },
});
