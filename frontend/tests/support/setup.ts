import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeAll, afterAll } from 'vitest';
import { server } from './mocks/server';

const storage = new Map<string, string>();
const localStorageMock: Storage = {
  get length() {
    return storage.size;
  },
  clear() {
    storage.clear();
  },
  getItem(key: string) {
    return storage.has(key) ? storage.get(key)! : null;
  },
  key(index: number) {
    return Array.from(storage.keys())[index] ?? null;
  },
  removeItem(key: string) {
    storage.delete(key);
  },
  setItem(key: string, value: string) {
    storage.set(key, value);
  },
};

Object.defineProperty(window, 'localStorage', {
  configurable: true,
  value: localStorageMock,
});
Object.defineProperty(globalThis, 'localStorage', {
  configurable: true,
  value: localStorageMock,
});
Object.defineProperty(Element.prototype, 'scrollIntoView', {
  configurable: true,
  value: () => {},
});

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
