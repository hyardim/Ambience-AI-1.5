import { describe, it, expect } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { Routes, Route } from 'react-router-dom';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { renderWithProviders, seedAuth } from '@test/utils';
import type { UserRole } from '@/types';
import { AuthContext } from '@/contexts/auth-context';

function TestChild() {
  return <div>Protected Content</div>;
}

function LoginStub() {
  return <div>Login Page</div>;
}

function AccessDeniedStub() {
  return <div>Access Denied</div>;
}

function renderRoute(allowedRoles: UserRole[] | undefined, initialRoute = '/protected') {
  return renderWithProviders(
    <Routes>
      <Route path="/login" element={<LoginStub />} />
      <Route path="/access-denied" element={<AccessDeniedStub />} />
      <Route
        path="/protected"
        element={
          <ProtectedRoute allowedRoles={allowedRoles}>
            <TestChild />
          </ProtectedRoute>
        }
      />
    </Routes>,
    { routes: [initialRoute] },
  );
}

describe('ProtectedRoute', () => {
  it('renders loading state while auth is resolving', () => {
    renderWithProviders(
      <Routes>
        <Route
          path="/protected"
          element={
            <AuthContext.Provider
              value={{
                token: null,
                username: null,
                email: null,
                role: null,
                isAuthenticated: false,
                isLoading: true,
                login: async () => 'gp',
                register: async () => 'gp',
                logout: () => {},
                setUserProfile: () => {},
              }}
            >
              <ProtectedRoute allowedRoles={['gp']}>
                <TestChild />
              </ProtectedRoute>
            </AuthContext.Provider>
          }
        />
      </Routes>,
      { routes: ['/protected'] },
    );

    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('redirects to /login when no auth token is present', async () => {
    // No localStorage seeded → user is unauthenticated after load
    renderRoute(['gp']);

    await waitFor(() => {
      expect(screen.getByText('Login Page')).toBeInTheDocument();
    });
  });

  it('redirects to /login when user is not authenticated', async () => {
    renderRoute(['gp']);

    await waitFor(() => {
      expect(screen.getByText('Login Page')).toBeInTheDocument();
    });
  });

  it('renders children when user is authenticated with an allowed role', async () => {
    seedAuth({ role: 'gp' });
    renderRoute(['gp']);

    await waitFor(() => {
      expect(screen.getByText('Protected Content')).toBeInTheDocument();
    });
  });

  it('redirects to /access-denied when user has wrong role', async () => {
    seedAuth({ role: 'gp' });
    renderRoute(['admin']);

    await waitFor(() => {
      expect(screen.getByText('Access Denied')).toBeInTheDocument();
    });
  });

  it('renders children when allowedRoles is undefined (any authenticated user)', async () => {
    seedAuth({ role: 'specialist' });
    renderRoute(undefined);

    await waitFor(() => {
      expect(screen.getByText('Protected Content')).toBeInTheDocument();
    });
  });

  it('allows admin to access GP routes when admin is in allowedRoles', async () => {
    seedAuth({ role: 'admin' });
    renderRoute(['gp', 'admin']);

    await waitFor(() => {
      expect(screen.getByText('Protected Content')).toBeInTheDocument();
    });
  });
});
