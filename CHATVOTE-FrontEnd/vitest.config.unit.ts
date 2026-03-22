import path from 'path';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['tests/unit/**/*.test.ts'],
    testTimeout: 10_000,
    reporters: ['verbose'],
  },
  resolve: {
    alias: {
      '@lib': path.resolve(__dirname, 'src/lib'),
      '@config': path.resolve(__dirname, 'src/config'),
      '@types': path.resolve(__dirname, 'src/types'),
      'server-only': path.resolve(__dirname, 'tests/eval/helpers/server-only-stub.ts'),
    },
  },
});
