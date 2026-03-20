import { describe, it, expect, beforeEach, vi } from 'vitest';
import CryptoJS from 'crypto-js';
import { secureStorage } from '@/utils/secureStorage';

describe('secureStorage', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('stores and retrieves encrypted values', () => {
    secureStorage.setItem('test-key', 'test-value');
    const result = secureStorage.getItem('test-key');
    expect(result).toBe('test-value');
  });

  it('returns null for missing keys', () => {
    expect(secureStorage.getItem('nonexistent')).toBeNull();
  });

  it('removes items', () => {
    secureStorage.setItem('key', 'value');
    secureStorage.removeItem('key');
    expect(secureStorage.getItem('key')).toBeNull();
  });

  it('stores encrypted data that differs from plaintext', () => {
    secureStorage.setItem('key', 'plaintext-value');
    const raw = localStorage.getItem('key');
    expect(raw).not.toBe('plaintext-value');
    expect(raw).toBeTruthy();
  });

  it('reads plaintext values as fallback (migration case)', () => {
    // Simulate a value stored before encryption was introduced
    localStorage.setItem('legacy-key', 'legacy-value');
    const result = secureStorage.getItem('legacy-key');
    // Should return the raw value since it cannot be decrypted
    expect(result).toBe('legacy-value');
  });

  it('handles multiple set/get cycles', () => {
    secureStorage.setItem('k1', 'value1');
    secureStorage.setItem('k2', 'value2');
    expect(secureStorage.getItem('k1')).toBe('value1');
    expect(secureStorage.getItem('k2')).toBe('value2');
  });

  it('overwrites existing values', () => {
    secureStorage.setItem('key', 'first');
    secureStorage.setItem('key', 'second');
    expect(secureStorage.getItem('key')).toBe('second');
  });

  it('falls back to plain text storage when encryption throws', () => {
    const encryptSpy = vi.spyOn(CryptoJS.AES, 'encrypt').mockImplementation(() => {
      throw new Error('Encryption failed');
    });

    secureStorage.setItem('encrypt-fail', 'plain-value');
    expect(localStorage.getItem('encrypt-fail')).toBe('plain-value');

    encryptSpy.mockRestore();
  });

  it('falls back to raw value when decryption throws', () => {
    const decryptSpy = vi.spyOn(CryptoJS.AES, 'decrypt').mockImplementation(() => {
      throw new Error('Decryption failed');
    });

    localStorage.setItem('decrypt-fail', 'corrupted-data');
    const result = secureStorage.getItem('decrypt-fail');
    expect(result).toBe('corrupted-data');

    decryptSpy.mockRestore();
  });
});
