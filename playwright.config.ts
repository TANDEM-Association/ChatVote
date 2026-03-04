import { defineConfig } from '/Users/adelinb/Documents/Projects/ChatVote/CHATVOTE-FrontEnd/node_modules/.pnpm/@playwright+test@1.58.2/node_modules/@playwright/test';

export default defineConfig({
  testDir: '.',
  testMatch: 'seed.spec.ts',
  use: {
    baseURL: 'http://localhost:3000',
  },
  webServer: [
    {
      command: 'npx ts-node --project /Users/adelinb/Documents/Projects/ChatVote/CHATVOTE-FrontEnd/tsconfig.json -e "const { startMockServer } = require(\'/Users/adelinb/Documents/Projects/ChatVote/CHATVOTE-FrontEnd/e2e/support/mock-socket-server\'); startMockServer(8080).then(() => { process.stdin.resume(); })"',
      url: 'http://localhost:8080',
      reuseExistingServer: true,
      timeout: 15000,
    },
    {
      command: 'npm run dev',
      cwd: '/Users/adelinb/Documents/Projects/ChatVote/CHATVOTE-FrontEnd',
      url: 'http://localhost:3000',
      reuseExistingServer: true,
      timeout: 60000,
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
      },
    },
  ],
});
