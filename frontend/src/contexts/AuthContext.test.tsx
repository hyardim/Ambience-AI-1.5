import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { renderHook, act, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { server } from '../test/mocks/server';
import { AuthProvider, useAuth } from './AuthContext';
import { mockLoginResponse } from '../test/mocks/handlers';

function wrapper({ children }: { children: React.ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}

describe('AuthContext', () => {
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
    localStorage.setItem('access_token', 'stored-token');
    localStorage.setItem('username', 'Stored User');
    localStorage.setItem('user_email', 'stored@example.com');
    localStorage.setItem('user_role', 'gp');

    const { result } = renderHook(() => useAuth(), { wrapper });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
    });

    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.token).toBe('stored-token');
    expect(result.current.username).toBe('Stored User');
    expect(result.current.role).toBe('gp');
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
    expect(localStorage.getItem('access_token')).toBe('mock-jwt-token');
    expect(localStorage.getItem('user_role')).toBe('gp');
  });

  it('register() updates state and localStorage', async () => {
    // Test register via a rendered component to avoid React 19 renderHook quirks
    let authState: any = null;
    let registerFn: any = null;

    function TestConsumer() {
      const auth = useAuth();
      authState = auth;
      registerFn = auth.register;
      return <div data-testid="loading">{String(auth.isLoading)}</div>;
    }

    await act(async () => {
      render(
        <AuthProvider>
          <TestConsumer />
        </AuthProvider>,
      );
    });

    expect(screen.getByTestId('loading')).toHaveTextContent('false');

    let role: string | undefined;
    await act(async () => {
      role = await registerFn({
        email: 'new@example.com',
        password: 'pass',
        role: 'gp',
      });
    });

    expect(role).toBe('gp');
    expect(authState.isAuthenticated).toBe(true);
    expect(localStorage.getItem('access_token')).toBe('mock-jwt-token');
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
    localStorage.setItem('access_token', 'stored-token');
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
    expect(localStorage.getItem('access_token')).toBeNull();
    expect(localStorage.getItem('username')).toBeNull();
    expect(localStorage.getItem('user_role')).toBeNull();
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
