import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { login as apiLogin, register as apiRegister } from '../services/api';
import type { RegisterRequest } from '../types/api';
import type { UserRole } from '../types';

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
  register: (payload: RegisterRequest) => Promise<UserRole>;
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

  // Restore token from localStorage on mount
  useEffect(() => {
    const token = localStorage.getItem('access_token');
    const username = localStorage.getItem('username');
    const role = localStorage.getItem('user_role') as UserRole | null;
    const email = localStorage.getItem('user_email');
    if (token) {
      setState({ token, username, email, role, isAuthenticated: true, isLoading: false });
    } else {
      setState(s => ({ ...s, isLoading: false }));
    }
  }, []);

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

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
