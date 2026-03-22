import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const getItemMock = vi.fn();
const removeItemMock = vi.fn();
const setHrefMock = vi.fn();

vi.mock('../utils/secureStorage', () => ({
  secureStorage: {
    getItem: getItemMock,
    removeItem: removeItemMock,
  },
}));

beforeEach(() => {
  getItemMock.mockReset();
  removeItemMock.mockReset();
  setHrefMock.mockReset();

  Object.defineProperty(window, 'location', {
    configurable: true,
    value: {
      pathname: '/gp/queries',
      set href(v: string) {
        setHrefMock(v);
      },
    },
  });
});

afterEach(() => {
  vi.resetModules();
});

describe('api/client', () => {
  it('adds bearer token when present', async () => {
    getItemMock.mockReturnValue('token-123');
    const { client } = await import('./client');

    const requestInterceptor = (client.interceptors.request as any).handlers[0].fulfilled;
    const cfg = requestInterceptor({ headers: {} });

    expect(cfg.headers.Authorization).toBe('Bearer token-123');
  });

  it('clears token and redirects on 401 response', async () => {
    const { client } = await import('./client');
    const responseReject = (client.interceptors.response as any).handlers[0].rejected;

    await expect(responseReject({ response: { status: 401 } })).rejects.toEqual({ response: { status: 401 } });
    expect(removeItemMock).toHaveBeenCalledWith('access_token');
    expect(setHrefMock).toHaveBeenCalledWith('/login');
  });
});
