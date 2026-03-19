import { render, type RenderOptions } from '@testing-library/react';
import { MemoryRouter, type MemoryRouterProps } from 'react-router-dom';
import { AuthProvider } from '../contexts/AuthContext';
import { secureStorage } from '../utils/secureStorage';
import type { ReactElement } from 'react';

interface WrapperOptions {
  /** Initial route entries for MemoryRouter (default: ['/']) */
  routes?: MemoryRouterProps['initialEntries'];
  /** Whether to wrap with AuthProvider (default: true) */
  withAuth?: boolean;
}

/**
 * Render helper that wraps the component with Router + AuthProvider.
 */
export function renderWithProviders(
  ui: ReactElement,
  options: WrapperOptions & Omit<RenderOptions, 'wrapper'> = {},
) {
  const { routes = ['/'], withAuth = true, ...renderOpts } = options;

  function Wrapper({ children }: { children: React.ReactNode }) {
    const content = <MemoryRouter initialEntries={routes}>{children}</MemoryRouter>;
    return withAuth ? <AuthProvider>{content}</AuthProvider> : content;
  }

  return render(ui, { wrapper: Wrapper, ...renderOpts });
}

/**
 * Seed encrypted storage with auth state so AuthContext restores it on mount.
 */
export function seedAuth(overrides: {
  token?: string;
  username?: string;
  email?: string;
  role?: string;
} = {}) {
  secureStorage.setItem('access_token', overrides.token ?? 'mock-jwt-token');
  secureStorage.setItem('username', overrides.username ?? 'Dr GP');
  secureStorage.setItem('user_email', overrides.email ?? 'gp@example.com');
  secureStorage.setItem('user_role', overrides.role ?? 'gp');
}
