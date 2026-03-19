import CryptoJS from 'crypto-js';
const AES = CryptoJS.AES;
const Utf8 = CryptoJS.enc.Utf8;

// Key sourced from env — falls back to a build-time constant so the app still
// works in dev without any extra config. In production, set VITE_STORAGE_KEY
// to a random string in your deployment environment.
const STORAGE_KEY = import.meta.env.VITE_STORAGE_KEY || 'ambience-ai-storage-dev-key';

export const secureStorage = {
  setItem(key: string, value: string): void {
    try {
      const encrypted = AES.encrypt(value, STORAGE_KEY).toString();
      localStorage.setItem(key, encrypted);
    } catch {
      // Fallback to plain text if encryption fails (should not happen)
      localStorage.setItem(key, value);
    }
  },

  getItem(key: string): string | null {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    try {
      const bytes = AES.decrypt(raw, STORAGE_KEY);
      const decrypted = bytes.toString(Utf8);
      // If decryption yields empty string the stored value was plaintext (migration case)
      return decrypted || raw;
    } catch {
      // Value was stored before encryption was introduced — return as-is
      return raw;
    }
  },

  removeItem(key: string): void {
    localStorage.removeItem(key);
  },
};
