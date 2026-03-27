import { render, type RenderOptions } from '@testing-library/react';
import { MemoryRouter, type MemoryRouterProps } from 'react-router-dom';
import type { ReactElement, ReactNode } from 'react';
import { AuthProvider } from '@/contexts/AuthContext';

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

  function Wrapper({ children }: { children: ReactNode }) {
    const content = <MemoryRouter initialEntries={routes}>{children}</MemoryRouter>;
    return withAuth ? <AuthProvider>{content}</AuthProvider> : content;
  }

  return render(ui, { wrapper: Wrapper, ...renderOpts });
}

/**
 * Seed localStorage with persisted identity so AuthContext restores it on mount.
 */
export function seedAuth(
  overrides: {
    username?: string;
    email?: string;
    role?: string;
  } = {},
) {
  localStorage.setItem('username', overrides.username ?? 'Dr GP');
  localStorage.setItem('user_email', overrides.email ?? 'gp@example.com');
  localStorage.setItem('user_role', overrides.role ?? 'gp');
}
