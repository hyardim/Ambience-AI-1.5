import { describe, expect, it, vi } from 'vitest';
import { getErrorMessage, ifNotAbortError, isAbortError } from '@/utils/errors';

describe('getErrorMessage', () => {
  it('returns the error message for Error instances', () => {
    expect(getErrorMessage(new Error('Boom'), 'Fallback')).toBe('Boom');
  });

  it('returns the fallback for non-Error values', () => {
    expect(getErrorMessage('Boom', 'Fallback')).toBe('Fallback');
  });

  it('detects abort errors correctly', () => {
    expect(isAbortError(new DOMException('Aborted', 'AbortError'))).toBe(true);
    expect(isAbortError(new Error('Boom'))).toBe(false);
  });

  it('runs the callback only for non-abort errors', () => {
    const callback = vi.fn();

    ifNotAbortError(new DOMException('Aborted', 'AbortError'), callback);
    expect(callback).not.toHaveBeenCalled();

    ifNotAbortError(new Error('Boom'), callback);
    expect(callback).toHaveBeenCalledTimes(1);
  });
});
