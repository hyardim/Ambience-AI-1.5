import { describe, it, expect, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Routes, Route } from 'react-router-dom';
import { server } from '../../test/mocks/server';
import { renderWithProviders, seedAuth } from '../../test/utils';
import { LoginPage } from './LoginPage';

function GPStub() {
  return <div>GP Queries Page</div>;
}
function SpecialistStub() {
  return <div>Specialist Page</div>;
}
function AdminStub() {
  return <div>Admin Page</div>;
}
function RegisterStub() {
  return <div>Register Page</div>;
}
function ResetStub() {
  return <div>Reset Password Page</div>;
}

function renderLogin(route = '/login') {
  return renderWithProviders(
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/gp/queries" element={<GPStub />} />
      <Route path="/specialist/queries" element={<SpecialistStub />} />
      <Route path="/admin/users" element={<AdminStub />} />
      <Route path="/register" element={<RegisterStub />} />
      <Route path="/reset-password" element={<ResetStub />} />
    </Routes>,
    { routes: [route] },
  );
}

describe('LoginPage', () => {
  it('renders the login form', async () => {
    renderLogin();

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /login to your account/i })).toBeInTheDocument();
    });

    expect(screen.getByLabelText(/username/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /login/i })).toBeInTheDocument();
  });

  it('shows validation error when fields are empty', async () => {
    renderLogin();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /login/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /login/i }));

    expect(screen.getByText(/please enter your email/i)).toBeInTheDocument();
  });

  it('fills demo credentials when the button is clicked', async () => {
    renderLogin();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/fill demo credentials/i)).toBeInTheDocument();
    });

    await user.click(screen.getByText(/fill demo credentials/i));

    expect(screen.getByLabelText(/username/i)).toHaveValue('gp@example.com');
    expect(screen.getByLabelText(/password/i)).toHaveValue('password123');
  });

  it('logs in and navigates to GP queries on success', async () => {
    renderLogin();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /login/i })).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/username/i), 'gp@example.com');
    await user.type(screen.getByLabelText(/password/i), 'password123');
    await user.click(screen.getByRole('button', { name: /login/i }));

    await waitFor(() => {
      expect(screen.getByText('GP Queries Page')).toBeInTheDocument();
    });
  });

  it('navigates to specialist page for specialist role', async () => {
    server.use(
      http.post('/auth/login', () => {
        return HttpResponse.json({
          access_token: 'tok',
          token_type: 'bearer',
          user: {
            id: 2,
            email: 'spec@example.com',
            full_name: 'Dr Spec',
            role: 'specialist',
            specialty: 'neurology',
            is_active: true,
          },
        });
      }),
    );

    renderLogin();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /login/i })).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/username/i), 'spec@example.com');
    await user.type(screen.getByLabelText(/password/i), 'pass');
    await user.click(screen.getByRole('button', { name: /login/i }));

    await waitFor(() => {
      expect(screen.getByText('Specialist Page')).toBeInTheDocument();
    });
  });

  it('navigates to admin page for admin role', async () => {
    server.use(
      http.post('/auth/login', () => {
        return HttpResponse.json({
          access_token: 'tok',
          token_type: 'bearer',
          user: {
            id: 3,
            email: 'admin@example.com',
            full_name: 'Admin',
            role: 'admin',
            specialty: null,
            is_active: true,
          },
        });
      }),
    );

    renderLogin();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /login/i })).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/username/i), 'admin@example.com');
    await user.type(screen.getByLabelText(/password/i), 'pass');
    await user.click(screen.getByRole('button', { name: /login/i }));

    await waitFor(() => {
      expect(screen.getByText('Admin Page')).toBeInTheDocument();
    });
  });

  it('shows error message on login failure', async () => {
    server.use(
      http.post('/auth/login', () => {
        return HttpResponse.json({ detail: 'Account locked' }, { status: 400 });
      }),
    );

    renderLogin();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /login/i })).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/username/i), 'bad@example.com');
    await user.type(screen.getByLabelText(/password/i), 'wrong');
    await user.click(screen.getByRole('button', { name: /login/i }));

    await waitFor(() => {
      expect(screen.getByText('Account locked')).toBeInTheDocument();
    });
  });

  it('toggles password visibility', async () => {
    renderLogin();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    });

    const passwordInput = screen.getByLabelText(/password/i);
    expect(passwordInput).toHaveAttribute('type', 'password');

    // Click the toggle button (it's the button wrapping the Eye icon)
    const toggleButton = passwordInput.parentElement!.querySelector('button')!;
    await user.click(toggleButton);

    expect(passwordInput).toHaveAttribute('type', 'text');
  });

  it('redirects already authenticated user to their role page', async () => {
    seedAuth({ role: 'gp' });
    renderLogin();

    await waitFor(() => {
      expect(screen.getByText('GP Queries Page')).toBeInTheDocument();
    });
  });

  it('has link to register page', async () => {
    renderLogin();

    await waitFor(() => {
      expect(screen.getByText(/register here/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/register here/i).closest('a')).toHaveAttribute('href', '/register');
  });

  it('has link to reset password page', async () => {
    renderLogin();

    await waitFor(() => {
      expect(screen.getByText(/forgot your password/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/forgot your password/i).closest('a')).toHaveAttribute('href', '/reset-password');
  });
});
