import { describe, it, expect } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { Routes, Route } from 'react-router-dom';
import { ProtectedRoute } from './ProtectedRoute';
import { renderWithProviders, seedAuth } from '../test/utils';

function TestChild() {
  return <div>Protected Content</div>;
}

function LoginStub() {
  return <div>Login Page</div>;
}

function AccessDeniedStub() {
  return <div>Access Denied</div>;
}

function renderRoute(allowedRoles: string[] | undefined, initialRoute = '/protected') {
  return renderWithProviders(
    <Routes>
      <Route path="/login" element={<LoginStub />} />
      <Route path="/access-denied" element={<AccessDeniedStub />} />
      <Route
        path="/protected"
        element={
          <ProtectedRoute allowedRoles={allowedRoles as any}>
            <TestChild />
          </ProtectedRoute>
        }
      />
    </Routes>,
    { routes: [initialRoute] },
  );
}

describe('ProtectedRoute', () => {
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
