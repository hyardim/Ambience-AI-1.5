/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react-swc';
import path from 'node:path';

function sanitizedExecArgv(argv: string[]): string[] {
  const cleaned: string[] = [];

  for (let index = 0; index < argv.length; index += 1) {
    const current = argv[index];

    // VS Code can inject this flag for extension-host processes; forwarding it
    // to test workers can trigger noisy "without a valid path" warnings.
    if (current === '--localstorage-file') {
      index += 1;
      continue;
    }

    if (current.startsWith('--localstorage-file=')) {
      continue;
    }

    cleaned.push(current);
  }

  if (!cleaned.includes('--no-warnings')) {
    cleaned.push('--no-warnings');
  }

  return cleaned;
}

const workerExecArgv = sanitizedExecArgv(process.execArgv);

export default defineConfig({
  plugins: [react()],
  define: {
    'import.meta.env.VITE_API_URL': JSON.stringify(''),
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
      '@test': path.resolve(__dirname, 'tests/support'),
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./tests/support/setup.ts'],
    include: ['tests/**/*.{test,spec}.{ts,tsx}'],
    execArgv: workerExecArgv,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/test/**',
        'src/vite-env.d.ts',
        'src/main.tsx',
        'src/**/*.d.ts',
        'src/types/**',
        'src/**/*.test.{ts,tsx}',
      ],
      thresholds: {
        lines: 100,
        branches: 98,
        functions: 100,
        statements: 99,
      },
    },
  },
});
