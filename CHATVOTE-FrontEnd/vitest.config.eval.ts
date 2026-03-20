import path from 'path';
import { loadEnv } from 'vite';
import { defineConfig } from 'vitest/config';

// Load .env + .env.local for API keys (SCALEWAY_EMBED_API_KEY, GOOGLE_GENERATIVE_AI_API_KEY, etc.)
const env = loadEnv('test', __dirname, '');
Object.assign(process.env, env);

export default defineConfig({
  test: {
    include: ['tests/eval/**/*.test.ts'],
    testTimeout: 180_000,
    hookTimeout: 30_000,
    pool: 'forks',
    reporters: ['verbose'],
  },
  resolve: {
    alias: {
      '@lib': path.resolve(__dirname, 'src/lib'),
      '@config': path.resolve(__dirname, 'src/config'),
      '@types': path.resolve(__dirname, 'src/types'),
      // Stub 'server-only' — it's a Next.js guard that errors outside Next runtime
      'server-only': path.resolve(__dirname, 'tests/eval/helpers/server-only-stub.ts'),
    },
  },
});
