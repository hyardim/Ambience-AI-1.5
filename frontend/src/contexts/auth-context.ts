import { createContext } from 'react';
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

export interface AuthContextValue extends AuthState {
  login: (username: string, password: string) => Promise<UserRole>;
  register: (payload: RegisterRequest) => Promise<UserRole>;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);
