import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Routes, Route } from 'react-router-dom';
import { LandingPage } from '@/pages/LandingPage';
import { renderWithProviders, seedAuth } from '@test/utils';
import { AuthContext, type AuthContextValue } from '@/contexts/auth-context';

function PortalStub({ label }: { label: string }) {
  return <div>{label}</div>;
}

function renderLanding(route = '/', authOverride?: Partial<AuthContextValue>) {
  const defaultAuth: AuthContextValue = {
    token: null,
    username: null,
    email: null,
    role: null,
    isAuthenticated: false,
    isLoading: false,
    login: vi.fn(),
    register: vi.fn(),
    logout: vi.fn(),
  };

  const content = (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route path="/gp/queries" element={<PortalStub label="GP Portal" />} />
      <Route path="/specialist/queries" element={<PortalStub label="Specialist Portal" />} />
      <Route path="/admin/users" element={<PortalStub label="Admin Portal" />} />
      <Route path="/login" element={<PortalStub label="Login Page" />} />
      <Route path="/register" element={<PortalStub label="Register Page" />} />
    </Routes>
  );

  return renderWithProviders(
    authOverride
      ? <AuthContext.Provider value={{ ...defaultAuth, ...authOverride }}>{content}</AuthContext.Provider>
      : content,
    { routes: [route] },
  );
}

describe('LandingPage', () => {
  it('shows login/register links when unauthenticated', () => {
    renderLanding();

    expect(screen.getByRole('link', { name: 'Login' })).toHaveAttribute('href', '/login');
    expect(screen.getByRole('link', { name: 'Register' })).toHaveAttribute('href', '/register');
  });

  it('shows signed-in state and admin panel for admin users', async () => {
    seedAuth({ role: 'admin', username: 'Admin User' });
    renderLanding();
    const user = userEvent.setup();

    expect(screen.getByText(/signed in as/i)).toBeInTheDocument();
    expect(screen.getByText(/Admin User/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Open Portal/i })).toHaveAttribute('href', '/admin/users');

    await user.click(screen.getByRole('link', { name: 'Open Portal' }));
    expect(screen.getByText('Admin Portal')).toBeInTheDocument();
  });

  it('routes specialist users to the specialist portal', async () => {
    seedAuth({ role: 'specialist', username: 'Dr Spec' });
    renderLanding();
    const user = userEvent.setup();

    await user.click(screen.getByRole('link', { name: 'Open Portal' }));
    expect(screen.getByText('Specialist Portal')).toBeInTheDocument();
  });

  it('routes gp users to the gp portal and supports logout', async () => {
    seedAuth({ role: 'gp', username: 'Dr GP' });
    renderLanding();
    const user = userEvent.setup();

    await user.click(screen.getByRole('link', { name: 'Open Portal' }));
    expect(screen.getByText('GP Portal')).toBeInTheDocument();

    renderLanding('/');
    await user.click(screen.getByRole('button', { name: /logout/i }));
    expect(screen.getByRole('link', { name: 'Login' })).toBeInTheDocument();
  });

  it('falls back to gp portal for unknown stored roles', () => {
    localStorage.setItem('access_token', 'stored-token');
    localStorage.setItem('username', 'Mystery User');
    localStorage.setItem('user_email', 'mystery@example.com');
    localStorage.setItem('user_role', 'mystery');

    renderLanding();

    expect(screen.getByText(/\(Unknown\)/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /open portal/i })).toHaveAttribute('href', '/gp/queries');
  });

  it('shows the loading session state and username fallback when auth is still resolving', () => {
    renderLanding('/', {
      isAuthenticated: true,
      username: '',
      email: null,
      role: 'gp',
      isLoading: true,
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
    });

    expect(screen.getByText(/checking session/i)).toBeInTheDocument();
  });

  it('falls back to a generic signed-in username when auth has no username', () => {
    renderLanding('/', {
      isAuthenticated: true,
      username: '',
      email: null,
      role: 'gp',
      isLoading: false,
      login: vi.fn(),
      register: vi.fn(),
      logout: vi.fn(),
    });

    expect(screen.getByText(/signed in as/i)).toBeInTheDocument();
    expect(screen.getByText(/user/i)).toBeInTheDocument();
  });
});
