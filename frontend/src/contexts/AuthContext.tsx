import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { login as apiLogin, register as apiRegister, logout as apiLogout } from '../services/api';
import type { RegisterRequest } from '../types/api';
import type { UserRole } from '../types';
import { secureStorage } from '../utils/secureStorage';

interface AuthState {
  token: string | null;
  username: string | null;
  email: string | null;
  role: UserRole | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

interface AuthContextValue extends AuthState {
  login: (username: string, password: string) => Promise<UserRole>;
  register: (payload: RegisterRequest) => Promise<{
    role: UserRole | null;
    requiresEmailVerification: boolean;
    message: string;
  }>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    token: null,
    username: null,
    email: null,
    role: null,
    isAuthenticated: false,
    isLoading: true,
  });

  // Restore token from storage on mount
  useEffect(() => {
    const token = secureStorage.getItem('access_token');
    const username = secureStorage.getItem('username');
    const role = secureStorage.getItem('user_role') as UserRole | null;
    const email = secureStorage.getItem('user_email');
    if (token) {
      setState({ token, username, email, role, isAuthenticated: true, isLoading: false });
    } else {
      setState(s => ({ ...s, isLoading: false }));
    }
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const data = await apiLogin(username, password);
    secureStorage.setItem('access_token', data.access_token);
    secureStorage.setItem('username', data.user.full_name || data.user.email);
    secureStorage.setItem('user_email', data.user.email);
    secureStorage.setItem('user_role', data.user.role);
    setState({
      token: data.access_token,
      username: data.user.full_name || data.user.email,
      email: data.user.email,
      role: data.user.role,
      isAuthenticated: true,
      isLoading: false,
    });
    return data.user.role;
  }, []);

  const register = useCallback(async (payload: RegisterRequest) => {
    const data = await apiRegister(payload);
    if (data.access_token) {
      secureStorage.setItem('access_token', data.access_token);
      secureStorage.setItem('username', data.user.full_name || data.user.email);
      secureStorage.setItem('user_email', data.user.email);
      secureStorage.setItem('user_role', data.user.role);
      setState({
        token: data.access_token,
        username: data.user.full_name || data.user.email,
        email: data.user.email,
        role: data.user.role,
        isAuthenticated: true,
        isLoading: false,
      });
      return {
        role: data.user.role,
        requiresEmailVerification: false,
        message: data.message,
      };
    }

    secureStorage.removeItem('access_token');
    secureStorage.removeItem('username');
    secureStorage.removeItem('user_email');
    secureStorage.removeItem('user_role');
    setState({ token: null, username: null, email: null, role: null, isAuthenticated: false, isLoading: false });
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
    secureStorage.removeItem('access_token');
    secureStorage.removeItem('username');
    secureStorage.removeItem('user_email');
    secureStorage.removeItem('user_role');
    setState({ token: null, username: null, email: null, role: null, isAuthenticated: false, isLoading: false });
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
