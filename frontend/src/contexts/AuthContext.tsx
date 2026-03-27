import { useCallback, useEffect, useState, type ReactNode } from 'react';

import {
  getProfile,
  login as apiLogin,
  logout as apiLogout,
  refreshSession,
  register as apiRegister,
} from '../services/api';
import type { RegisterRequest, UserProfile } from '../types/api';
import type { UserRole } from '../types';
import { isAbortError } from '../utils/errors';
import { secureStorage } from '../utils/secureStorage';
import { AuthContext } from './auth-context';

interface AuthState {
  token: string | null;
  username: string | null;
  email: string | null;
  role: UserRole | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

function readStoredIdentity(): Omit<AuthState, 'token' | 'isLoading'> {
  const username = localStorage.getItem('username');
  const email = localStorage.getItem('user_email');
  const role = localStorage.getItem('user_role') as UserRole | null;

  if (!email || !role) {
    return {
      username: null,
      email: null,
      role: null,
      isAuthenticated: false,
    };
  }

  return {
    username,
    email,
    role,
    isAuthenticated: true,
  };
}

function persistIdentity(user: Pick<UserProfile, 'full_name' | 'email' | 'role'>): void {
  localStorage.setItem('username', user.full_name || user.email);
  localStorage.setItem('user_email', user.email);
  localStorage.setItem('user_role', user.role);
}

function clearIdentity(): void {
  secureStorage.removeItem('access_token');
  localStorage.removeItem('username');
  localStorage.removeItem('user_email');
  localStorage.removeItem('user_role');
}

function buildStateFromUser(
  user: Pick<UserProfile, 'full_name' | 'email' | 'role'>,
  token: string | null,
): AuthState {
  return {
    token,
    username: user.full_name || user.email,
    email: user.email,
    role: user.role,
    isAuthenticated: true,
    isLoading: false,
  };
}

function isTransientAuthBootstrapError(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false;
  }
  const message = error.message.toLowerCase();
  return (
    message.includes('too many requests') ||
    message.includes('rate limit') ||
    message.includes('failed to fetch') ||
    message.includes('networkerror') ||
    message.includes('request failed (5')
  );
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const storedIdentity = readStoredIdentity();
  const [state, setState] = useState<AuthState>({
    token: secureStorage.getItem('access_token'),
    ...storedIdentity,
    isLoading: storedIdentity.isAuthenticated,
  });

  const setUserProfile = useCallback((user: Pick<UserProfile, 'full_name' | 'email' | 'role'>) => {
    persistIdentity(user);
    setState((prev) => buildStateFromUser(user, prev.token));
  }, []);

  useEffect(() => {
    if (!storedIdentity.isAuthenticated) {
      return;
    }

    let cancelled = false;
    const controller = new AbortController();

    void refreshSession({ signal: controller.signal })
      .then((data) => {
        if (cancelled) return;
        persistIdentity(data.user);
        setState(buildStateFromUser(data.user, data.access_token));
      })
      .catch(async () => {
        if (cancelled) return;
        try {
          const profile = await getProfile({ signal: controller.signal });
          if (cancelled) return;
          persistIdentity(profile);
          setState(buildStateFromUser(profile, null));
          return;
        } catch (error) {
          if (isAbortError(error)) return;
          if (cancelled) return;
          if (isTransientAuthBootstrapError(error)) {
            // Keep the existing local identity on temporary outages/rate limits.
            setState((prev) => ({
              ...prev,
              isLoading: false,
            }));
            return;
          }
          clearIdentity();
          setState({
            token: null,
            username: null,
            email: null,
            role: null,
            isAuthenticated: false,
            isLoading: false,
          });
        }
      });

    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [storedIdentity.isAuthenticated]);

  const login = useCallback(async (username: string, password: string) => {
    const data = await apiLogin(username, password);
    persistIdentity(data.user);
    setState(buildStateFromUser(data.user, data.access_token));
    return data.user.role;
  }, []);

  const register = useCallback(async (payload: RegisterRequest) => {
    const data = await apiRegister(payload);
    if (data.access_token) {
      persistIdentity(data.user);
      setState(buildStateFromUser(data.user, data.access_token));
      return {
        role: data.user.role,
        requiresEmailVerification: false,
        message: data.message,
      };
    }

    clearIdentity();
    setState({
      token: null,
      username: null,
      email: null,
      role: null,
      isAuthenticated: false,
      isLoading: false,
    });
    return {
      role: null,
      requiresEmailVerification: data.requires_email_verification,
      message: data.message,
    };
  }, []);

  const logout = useCallback(() => {
    void apiLogout().catch(() => {
      // Best-effort server-side logout; local session is still cleared below.
    });
    clearIdentity();
    setState({
      token: null,
      username: null,
      email: null,
      role: null,
      isAuthenticated: false,
      isLoading: false,
    });
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, register, logout, setUserProfile }}>
      {children}
    </AuthContext.Provider>
  );
}
