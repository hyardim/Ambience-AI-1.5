import { describe, it, expect } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Routes, Route } from 'react-router-dom';
import { server } from '@test/mocks/server';
import { renderWithProviders, seedAuth } from '@test/utils';
import { LoginPage } from '@/pages/auth/LoginPage';

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
function ForgotStub() {
  return <div>Forgot Password Page</div>;
}
function ResendVerificationStub() {
  return <div>Resend Verification Page</div>;
}

function renderLogin(route = '/login') {
  return renderWithProviders(
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/gp/queries" element={<GPStub />} />
      <Route path="/specialist/queries" element={<SpecialistStub />} />
      <Route path="/admin/users" element={<AdminStub />} />
      <Route path="/register" element={<RegisterStub />} />
      <Route path="/forgot-password" element={<ForgotStub />} />
      <Route path="/resend-verification" element={<ResendVerificationStub />} />
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

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /login/i })).toBeInTheDocument();
    });

    fireEvent.submit(screen.getByRole('button', { name: /login/i }).closest('form')!);

    expect(screen.getByText(/email is required/i)).toBeInTheDocument();
  });

  it('shows validation error when email format is invalid', async () => {
    renderLogin();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /login/i })).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/username/i), 'invalid-email');
    await user.type(screen.getByLabelText(/password/i), 'Password123!');
    fireEvent.submit(screen.getByRole('button', { name: /login/i }).closest('form')!);

    expect(screen.getByText(/please enter a valid email address/i)).toBeInTheDocument();
  });

  it('logs in and navigates to GP queries on success', async () => {
    renderLogin();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /login/i })).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/username/i), 'gp@example.com');
    await user.type(screen.getByLabelText(/password/i), 'Password123');
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
            email_verified: true,
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
            email_verified: true,
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

  it('maps invalid, deactivated, and rate-limited login errors to friendly messages', async () => {
    const user = userEvent.setup();

    server.use(
      http.post('/auth/login', () =>
        HttpResponse.json({ detail: 'Incorrect email or password' }, { status: 400 }),
      ),
    );
    renderLogin();

    await user.type(screen.getByLabelText(/username/i), 'bad@example.com');
    await user.type(screen.getByLabelText(/password/i), 'wrong');
    await user.click(screen.getByRole('button', { name: /login/i }));

    await waitFor(() => {
      expect(screen.getByText(/invalid email or password/i)).toBeInTheDocument();
    });

    server.use(
      http.post('/auth/login', () =>
        HttpResponse.json({ detail: 'Account deactivated' }, { status: 403 }),
      ),
    );
    await user.click(screen.getByRole('button', { name: /login/i }));

    await waitFor(() => {
      expect(screen.getByText(/^Account deactivated$/i)).toBeInTheDocument();
    });

    server.use(
      http.post('/auth/login', () =>
        HttpResponse.json({ detail: 'Too many attempts' }, { status: 429 }),
      ),
    );
    await user.click(screen.getByRole('button', { name: /login/i }));

    await waitFor(() => {
      expect(screen.getByText(/too many attempts, please wait/i)).toBeInTheDocument();
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

    expect(screen.getByText(/forgot your password/i).closest('a')).toHaveAttribute(
      'href',
      '/forgot-password',
    );
  });

  it('shows resend verification guidance when login is blocked for unverified email', async () => {
    server.use(
      http.post('/auth/login', () => {
        return HttpResponse.json(
          {
            detail:
              'Please verify your email before logging in. You can request a new verification email.',
          },
          { status: 403 },
        );
      }),
    );

    renderLogin();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/username/i), 'gp@example.com');
    await user.type(screen.getByLabelText(/password/i), 'Password123');
    await user.click(screen.getByRole('button', { name: /login/i }));

    await waitFor(() => {
      expect(screen.getByText(/resend verification email/i)).toBeInTheDocument();
    });
  });
});
