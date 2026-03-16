import { describe, expect, it } from 'vitest';
import { setOptionalSearchParam } from '@/utils/url';

describe('url utils', () => {
  it('sets search params only when values are present', () => {
    const params = new URLSearchParams();

    setOptionalSearchParam(params, 'action', 'LOGIN');
    setOptionalSearchParam(params, 'limit', 5);
    setOptionalSearchParam(params, 'empty', '');
    setOptionalSearchParam(params, 'zero', 0);
    setOptionalSearchParam(params, 'missing', undefined);

    expect(params.get('action')).toBe('LOGIN');
    expect(params.get('limit')).toBe('5');
    expect(params.get('empty')).toBeNull();
    expect(params.get('zero')).toBeNull();
    expect(params.get('missing')).toBeNull();
  });
});
