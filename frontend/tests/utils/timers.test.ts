import { describe, expect, it, vi, afterEach } from 'vitest';
import { resetTimeout, resetTimeoutWithValue } from '@/utils/timers';

describe('timers', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('replaces an existing timeout before scheduling a new one', () => {
    vi.useFakeTimers();
    const ref = { current: null as ReturnType<typeof setTimeout> | null };
    const callback = vi.fn();

    resetTimeout(ref, callback, 200);
    resetTimeout(ref, callback, 200);
    vi.advanceTimersByTime(200);

    expect(callback).toHaveBeenCalledTimes(1);
  });

  it('passes the provided value through resetTimeoutWithValue', () => {
    vi.useFakeTimers();
    const ref = { current: null as ReturnType<typeof setTimeout> | null };
    const callback = vi.fn();

    resetTimeoutWithValue(ref, callback, 'query', 100);
    vi.advanceTimersByTime(100);

    expect(callback).toHaveBeenCalledWith('query');
  });
});
