import { describe, expect, it, vi } from 'vitest';
import { nextTimeoutPhase, settleResolver } from '@/utils/chatStream';

describe('chatStream utils', () => {
  it('settles only once', () => {
    const resolve = vi.fn();
    const first = settleResolver(false, resolve);
    const second = settleResolver(true, resolve);
    expect(first).toBe(true);
    expect(second).toBe(false);
    expect(resolve).toHaveBeenCalledTimes(1);
  });

  it('keeps the phase unless still connecting', () => {
    expect(nextTimeoutPhase('connecting')).toBe('fallback_polling');
    expect(nextTimeoutPhase('streaming')).toBe('streaming');
  });
});
