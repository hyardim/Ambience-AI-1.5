import { describe, expect, it } from 'vitest';
import { coalesce, orFallback } from '@/utils/value';

describe('orFallback', () => {
  it('returns the original value when it is present', () => {
    expect(orFallback('gp', 'fallback')).toBe('gp');
  });

  it('returns the fallback for nullish or empty values', () => {
    expect(orFallback('', 'fallback')).toBe('fallback');
    expect(orFallback(null, 'fallback')).toBe('fallback');
    expect(orFallback(undefined, 'fallback')).toBe('fallback');
  });

  it('coalesces only nullish values', () => {
    expect(coalesce('', 'fallback')).toBe('');
    expect(coalesce(false, true)).toBe(false);
    expect(coalesce(null, 'fallback')).toBe('fallback');
    expect(coalesce(undefined, 'fallback')).toBe('fallback');
  });
});
