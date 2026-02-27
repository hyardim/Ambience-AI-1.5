import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeAll, afterAll } from 'vitest';
import { server } from './mocks/server';

// Start MSW server before all tests
beforeAll(() => server.listen({ onUnhandledRequest: 'warn' }));

// Reset handlers after each test so they don't leak between tests
afterEach(() => {
  cleanup();
  server.resetHandlers();
  localStorage.clear();
});

// Clean up after all tests
afterAll(() => server.close());

// Stub window.confirm to always return true (override per-test as needed)
Object.defineProperty(window, 'confirm', {
  writable: true,
  value: () => true,
});
