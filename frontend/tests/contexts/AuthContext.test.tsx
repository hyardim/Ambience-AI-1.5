import { afterEach, describe, it, expect, vi } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { server } from '@test/mocks/server';
import { AuthProvider } from '@/contexts/AuthContext';
import { useAuth } from '@/contexts/useAuth';
import type { RegisterRequest } from '@/types/api';
import * as api from '@/services/api';
import { secureStorage } from '@/utils/secureStorage';

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function wrapper({ children }: { children: React.ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}

describe('AuthContext', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('resolves to unauthenticated when no token stored', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });

    // Wait for the initial effect to settle
    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.token).toBeNull();
  });

  it('restores session from localStorage on mount', async () => {
    localStorage.setItem('username', 'Stored User');
    localStorage.setItem('user_email', 'stored@example.com');
    localStorage.setItem('user_role', 'gp');

    const { result } = renderHook(() => useAuth(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.token).toBe('mock-jwt-token');
    expect(result.current.username).toBe('Stored User');
    expect(result.current.role).toBe('gp');
    expect(secureStorage.getItem('access_token')).toBe('mock-jwt-token');
  });

  it('falls back to loading profile when refresh fails but session is still valid', async () => {
    localStorage.setItem('username', 'Stored User');
    localStorage.setItem('user_email', 'stored@example.com');
    localStorage.setItem('user_role', 'gp');
    server.use(
      http.post('/auth/refresh', () =>
        HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 }),
      ),
      http.get('/auth/me', () =>
        HttpResponse.json({
          id: 1,
          email: 'stored@example.com',
          full_name: 'Recovered User',
          role: 'gp',
          specialty: null,
          is_active: true,
        }),
      ),
    );

    const { result } = renderHook(() => useAuth(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.username).toBe('Recovered User');
  });

  it('clears identity when both refresh and profile recovery fail', async () => {
    localStorage.setItem('username', 'Stored User');
    localStorage.setItem('user_email', 'stored@example.com');
    localStorage.setItem('user_role', 'gp');
    server.use(
      http.post('/auth/refresh', () =>
        HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 }),
      ),
      http.get('/auth/me', () => HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 })),
    );

    const { result } = renderHook(() => useAuth(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.isAuthenticated).toBe(false);
    expect(localStorage.getItem('username')).toBeNull();
    expect(localStorage.getItem('user_email')).toBeNull();
    expect(localStorage.getItem('user_role')).toBeNull();
  });

  it('does not update state after unmount when refresh fails late', async () => {
    const refreshGate = deferred<void>();
    let profileCalls = 0;
    localStorage.setItem('username', 'Stored User');
    localStorage.setItem('user_email', 'stored@example.com');
    localStorage.setItem('user_role', 'gp');
    server.use(
      http.post('/auth/refresh', async () => {
        await refreshGate.promise;
        return HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 });
      }),
      http.get('/auth/me', () => {
        profileCalls += 1;
        return HttpResponse.json({
          id: 1,
          email: 'stored@example.com',
          full_name: 'Recovered User',
          role: 'gp',
          specialty: null,
          is_active: true,
        });
      }),
    );

    const { unmount } = renderHook(() => useAuth(), { wrapper });
    unmount();
    refreshGate.resolve();

    await act(async () => {
      await Promise.resolve();
    });

    expect(profileCalls).toBe(0);
  });

  it('does not update state after unmount when refresh succeeds late', async () => {
    const refreshGate = deferred<void>();
    const refreshSpy = vi.spyOn(api, 'refreshSession').mockImplementationOnce(async () => {
      await refreshGate.promise;
      return {
        access_token: 'late-token',
        token_type: 'bearer',
        user: {
          id: 1,
          email: 'stored@example.com',
          full_name: 'Late User',
          role: 'gp',
          specialty: null,
          is_active: true,
        },
      };
    });
    localStorage.setItem('username', 'Stored User');
    localStorage.setItem('user_email', 'stored@example.com');
    localStorage.setItem('user_role', 'gp');

    const { result, unmount } = renderHook(() => useAuth(), { wrapper });
    unmount();
    refreshGate.resolve();

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.username).toBe('Stored User');
    expect(localStorage.getItem('username')).toBe('Stored User');
    expect(refreshSpy).toHaveBeenCalled();
  });

  it('does not update state after unmount during profile fallback', async () => {
    const profileGate = deferred<void>();
    localStorage.setItem('username', 'Stored User');
    localStorage.setItem('user_email', 'stored@example.com');
    localStorage.setItem('user_role', 'gp');
    server.use(
      http.post('/auth/refresh', () =>
        HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 }),
      ),
      http.get('/auth/me', async () => {
        await profileGate.promise;
        return HttpResponse.json({
          id: 1,
          email: 'stored@example.com',
          full_name: 'Recovered User',
          role: 'gp',
          specialty: null,
          is_active: true,
        });
      }),
    );

    const { unmount } = renderHook(() => useAuth(), { wrapper });
    await act(async () => {
      await Promise.resolve();
    });
    unmount();
    profileGate.resolve();

    await act(async () => {
      await Promise.resolve();
    });

    expect(localStorage.getItem('username')).not.toBe('Recovered User');
  });

  it('silently ignores aborted profile fallback requests', async () => {
    const profileGate = deferred<void>();
    const refreshSpy = vi
      .spyOn(api, 'refreshSession')
      .mockRejectedValueOnce(new Error('refresh failed'));
    const profileSpy = vi.spyOn(api, 'getProfile').mockImplementationOnce(async () => {
      await profileGate.promise;
      throw new DOMException('Aborted', 'AbortError');
    });
    localStorage.setItem('username', 'Stored User');
    localStorage.setItem('user_email', 'stored@example.com');
    localStorage.setItem('user_role', 'gp');

    const { result, unmount } = renderHook(() => useAuth(), { wrapper });
    await act(async () => {
      await Promise.resolve();
    });
    unmount();
    profileGate.resolve();

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.username).toBe('Stored User');
    expect(refreshSpy).toHaveBeenCalled();
    expect(profileSpy).toHaveBeenCalled();
  });

  it('does not update state when profile fallback succeeds after logical cancellation', async () => {
    const profileGate = deferred<void>();
    const refreshSpy = vi
      .spyOn(api, 'refreshSession')
      .mockRejectedValueOnce(new Error('refresh failed'));
    const profileSpy = vi.spyOn(api, 'getProfile').mockImplementationOnce(async () => {
      await profileGate.promise;
      return {
        id: 1,
        email: 'stored@example.com',
        full_name: 'Recovered User',
        role: 'gp',
        specialty: null,
        is_active: true,
      };
    });
    localStorage.setItem('username', 'Stored User');
    localStorage.setItem('user_email', 'stored@example.com');
    localStorage.setItem('user_role', 'gp');

    const { result, unmount } = renderHook(() => useAuth(), { wrapper });
    await act(async () => {
      await Promise.resolve();
    });
    unmount();
    profileGate.resolve();

    await act(async () => {
      await Promise.resolve();
    });

    expect(result.current.username).toBe('Stored User');
    expect(localStorage.getItem('username')).toBe('Stored User');
    expect(refreshSpy).toHaveBeenCalled();
    expect(profileSpy).toHaveBeenCalled();
  });

  it('does not clear state twice after unmount when profile fallback also fails', async () => {
    const profileGate = deferred<void>();
    localStorage.setItem('username', 'Stored User');
    localStorage.setItem('user_email', 'stored@example.com');
    localStorage.setItem('user_role', 'gp');
    server.use(
      http.post('/auth/refresh', () =>
        HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 }),
      ),
      http.get('/auth/me', async () => {
        await profileGate.promise;
        return HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 });
      }),
    );

    const { unmount } = renderHook(() => useAuth(), { wrapper });
    await act(async () => {
      await Promise.resolve();
    });
    unmount();
    profileGate.resolve();

    await act(async () => {
      await Promise.resolve();
    });

    expect(localStorage.getItem('username')).toBeNull();
    expect(localStorage.getItem('user_email')).toBeNull();
    expect(localStorage.getItem('user_role')).toBeNull();
  });

  it('login() updates state and localStorage', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    let role: string | undefined;
    await act(async () => {
      role = await result.current.login('gp@example.com', 'password123');
    });

    expect(role).toBe('gp');
    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.token).toBe('mock-jwt-token');
    expect(localStorage.getItem('user_role')).toBe('gp');
    expect(secureStorage.getItem('access_token')).toBe('mock-jwt-token');
  });

  it('register() updates state and localStorage', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });

    await waitFor(() => expect(result.current.isLoading).toBe(false));

    let role:
      | {
          role: string | null;
          requiresEmailVerification: boolean;
          message: string;
        }
      | undefined;
    await act(async () => {
      role = await result.current.register({
        email: 'new@example.com',
        password: 'pass',
        role: 'gp',
      } satisfies RegisterRequest);
    });

    expect(role).toEqual({
      role: 'gp',
      requiresEmailVerification: false,
      message: 'Registration successful',
    });
    expect(result.current.isAuthenticated).toBe(true);
    expect(localStorage.getItem('user_email')).toBe('new@example.com');
    expect(secureStorage.getItem('access_token')).toBe('mock-jwt-token');
  });

  it('register() falls back to email when full_name is missing', async () => {
    server.use(
      http.post('/auth/register', () =>
        HttpResponse.json({
          access_token: 'mock-jwt-token',
          token_type: 'bearer',
          user: {
            id: 11,
            email: 'register-fallback@example.com',
            full_name: null,
            role: 'gp',
            specialty: null,
            is_active: true,
          },
        }),
      ),
    );

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.register({
        email: 'register-fallback@example.com',
        password: 'pass',
        role: 'gp',
      } satisfies RegisterRequest);
    });

    expect(result.current.username).toBe('register-fallback@example.com');
    expect(localStorage.getItem('username')).toBe('register-fallback@example.com');
  });

  it('falls back to email when full_name is missing', async () => {
    server.use(
      http.post('/auth/login', () =>
        HttpResponse.json({
          access_token: 'mock-jwt-token',
          token_type: 'bearer',
          user: {
            id: 10,
            email: 'fallback@example.com',
            full_name: null,
            role: 'gp',
            specialty: null,
            is_active: true,
          },
        }),
      ),
    );

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.login('fallback@example.com', 'password123');
    });

    expect(result.current.username).toBe('fallback@example.com');
    expect(localStorage.getItem('username')).toBe('fallback@example.com');
  });

  it('login() rejects on API failure', async () => {
    server.use(
      http.post('/auth/login', () => {
        return HttpResponse.json({ detail: 'Invalid credentials' }, { status: 400 });
      }),
    );

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    // Catch inside act() so the rejection doesn't corrupt React 19 internal state
    let error: Error | undefined;
    await act(async () => {
      try {
        await result.current.login('bad', 'creds');
      } catch (e) {
        error = e as Error;
      }
    });

    expect(error?.message).toBe('Invalid credentials');
    expect(result.current.isAuthenticated).toBe(false);
  });

  it('logout() clears state and localStorage', async () => {
    localStorage.setItem('username', 'User');
    localStorage.setItem('user_email', 'user@example.com');
    localStorage.setItem('user_role', 'gp');

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isAuthenticated).toBe(true));

    act(() => {
      result.current.logout();
    });

    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.token).toBeNull();
    expect(localStorage.getItem('username')).toBeNull();
    expect(localStorage.getItem('user_role')).toBeNull();
    expect(secureStorage.getItem('access_token')).toBeNull();
  });

  it('logout() still clears local state when api logout fails', async () => {
    server.use(
      http.post('/auth/logout', () => HttpResponse.json({ detail: 'Nope' }, { status: 500 })),
    );
    localStorage.setItem('username', 'User');
    localStorage.setItem('user_email', 'user@example.com');
    localStorage.setItem('user_role', 'gp');

    const { result } = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(result.current.isAuthenticated).toBe(true));

    act(() => {
      result.current.logout();
    });

    expect(result.current.isAuthenticated).toBe(false);
    expect(localStorage.getItem('user_email')).toBeNull();
  });

  it('throws when useAuth is used outside AuthProvider', () => {
    // Suppress console.error for the expected React error
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => {
      renderHook(() => useAuth());
    }).toThrow('useAuth must be used within AuthProvider');
    spy.mockRestore();
  });
});
