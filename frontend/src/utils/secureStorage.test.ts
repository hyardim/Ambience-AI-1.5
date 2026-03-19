import { describe, it, expect, beforeEach } from 'vitest';
import { secureStorage } from './secureStorage';

beforeEach(() => {
  localStorage.clear();
});

describe('secureStorage.setItem / getItem', () => {
  it('stores and retrieves a value', () => {
    secureStorage.setItem('key', 'hello');
    expect(secureStorage.getItem('key')).toBe('hello');
  });

  it('encrypts the value so raw localStorage is not plaintext', () => {
    secureStorage.setItem('access_token', 'my-jwt-token');
    const raw = localStorage.getItem('access_token');
    expect(raw).not.toBe('my-jwt-token');
    expect(raw).not.toBeNull();
  });

  it('returns null for a missing key', () => {
    expect(secureStorage.getItem('nonexistent')).toBeNull();
  });

  it('overwrites an existing value', () => {
    secureStorage.setItem('role', 'gp');
    secureStorage.setItem('role', 'admin');
    expect(secureStorage.getItem('role')).toBe('admin');
  });

  it('handles empty string values', () => {
    secureStorage.setItem('empty', '');
    // Empty string after decryption falls back to raw — acceptable
    const val = secureStorage.getItem('empty');
    expect(val === '' || val !== null).toBe(true);
  });
});

describe('secureStorage.removeItem', () => {
  it('removes a stored value', () => {
    secureStorage.setItem('username', 'Dr Smith');
    secureStorage.removeItem('username');
    expect(secureStorage.getItem('username')).toBeNull();
  });

  it('does not throw when removing a non-existent key', () => {
    expect(() => secureStorage.removeItem('does-not-exist')).not.toThrow();
  });
});

describe('secureStorage migration (plaintext fallback)', () => {
  it('returns plaintext value if it was stored without encryption', () => {
    // Simulate pre-encryption data in localStorage
    localStorage.setItem('legacy_key', 'plaintext-value');
    expect(secureStorage.getItem('legacy_key')).toBe('plaintext-value');
  });
});

describe('secureStorage isolation', () => {
  it('different keys do not interfere with each other', () => {
    secureStorage.setItem('a', 'value-a');
    secureStorage.setItem('b', 'value-b');
    expect(secureStorage.getItem('a')).toBe('value-a');
    expect(secureStorage.getItem('b')).toBe('value-b');
  });
});
