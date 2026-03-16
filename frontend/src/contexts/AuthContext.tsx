import { useState, useCallback, type ReactNode } from 'react';
import { login as apiLogin, register as apiRegister, logout as apiLogout } from '../services/api';
import type { RegisterRequest } from '../types/api';
import type { UserRole } from '../types';
import { AuthContext } from './auth-context';

interface AuthState {
  token: string | null;
  username: string | null;
  email: string | null;
  role: UserRole | null;
  isAuthenticated: boolean;
  isLoading: boolean;
}

function getInitialAuthState(): AuthState {
  const token = localStorage.getItem('access_token');
  const username = localStorage.getItem('username');
  const role = localStorage.getItem('user_role') as UserRole | null;
  const email = localStorage.getItem('user_email');

  if (!token) {
    return {
      token: null,
      username: null,
      email: null,
      role: null,
      isAuthenticated: false,
      isLoading: false,
    };
  }

  return {
    token,
    username,
    email,
    role,
    isAuthenticated: true,
    isLoading: false,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(getInitialAuthState);

  const login = useCallback(async (username: string, password: string) => {
    const data = await apiLogin(username, password);
    localStorage.setItem('access_token', data.access_token);
    localStorage.setItem('username', data.user.full_name || data.user.email);
    localStorage.setItem('user_email', data.user.email);
    localStorage.setItem('user_role', data.user.role);
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
    localStorage.setItem('access_token', data.access_token);
    localStorage.setItem('username', data.user.full_name || data.user.email);
    localStorage.setItem('user_email', data.user.email);
    localStorage.setItem('user_role', data.user.role);
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

  const logout = useCallback(() => {
    void apiLogout().catch(() => {
      // Best-effort server-side logout; local session is still cleared below.
    });
    localStorage.removeItem('access_token');
    localStorage.removeItem('username');
    localStorage.removeItem('user_email');
    localStorage.removeItem('user_role');
    setState({ token: null, username: null, email: null, role: null, isAuthenticated: false, isLoading: false });
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
