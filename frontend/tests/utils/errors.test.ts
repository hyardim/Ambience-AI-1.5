import { describe, expect, it } from 'vitest';
import { getErrorMessage } from '@/utils/errors';

describe('getErrorMessage', () => {
  it('returns the error message for Error instances', () => {
    expect(getErrorMessage(new Error('Boom'), 'Fallback')).toBe('Boom');
  });

  it('returns the fallback for non-Error values', () => {
    expect(getErrorMessage('Boom', 'Fallback')).toBe('Fallback');
  });
});
