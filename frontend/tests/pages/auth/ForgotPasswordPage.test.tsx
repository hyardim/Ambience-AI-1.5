import { describe, it, expect, vi } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Routes, Route } from 'react-router-dom';
import { server } from '@test/mocks/server';
import { renderWithProviders } from '@test/utils';
import { ForgotPasswordPage } from '@/pages/auth/ForgotPasswordPage';
import * as api from '@/services/api';

function LoginStub() {
  return <div>Login Page</div>;
}

function renderForgotPassword() {
  return renderWithProviders(
    <Routes>
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/login" element={<LoginStub />} />
    </Routes>,
    { routes: ['/forgot-password'] },
  );
}

describe('ForgotPasswordPage', () => {
  it('renders the form', async () => {
    renderForgotPassword();

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /forgot your password/i })).toBeInTheDocument();
    });

    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /send reset link/i })).toBeInTheDocument();
  });

  it('shows error when submitting empty email', async () => {
    renderForgotPassword();

    const form = screen.getByRole('button', { name: /send reset link/i }).closest('form')!;
    fireEvent.submit(form);

    expect(screen.getByText(/email is required/i)).toBeInTheDocument();
  });

  it('shows error when email format is invalid', async () => {
    renderForgotPassword();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email address/i), 'invalid-email');
    fireEvent.submit(screen.getByRole('button', { name: /send reset link/i }).closest('form')!);

    expect(screen.getByText(/please enter a valid email address/i)).toBeInTheDocument();
  });

  it('calls forgotPassword API on submit and shows success message', async () => {
    renderForgotPassword();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email address/i), 'test@example.com');
    await user.click(screen.getByRole('button', { name: /send reset link/i }));

    await waitFor(() => {
      expect(screen.getByText(/password reset link/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/back to login/i)).toBeInTheDocument();
  });

  it('shows error on API failure', async () => {
    server.use(
      http.post('/auth/forgot-password', () =>
        HttpResponse.json({ detail: 'Rate limit exceeded' }, { status: 429 })),
    );

    renderForgotPassword();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email address/i), 'test@example.com');
    await user.click(screen.getByRole('button', { name: /send reset link/i }));

    await waitFor(() => {
      expect(screen.getByText(/too many requests/i)).toBeInTheDocument();
    });
  });

  it('shows fallback error for non-Error exceptions', async () => {
    server.use(
      http.post('/auth/forgot-password', () =>
        new HttpResponse(null, { status: 500 })),
    );

    renderForgotPassword();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email address/i), 'test@example.com');
    await user.click(screen.getByRole('button', { name: /send reset link/i }));

    await waitFor(() => {
      expect(screen.getByText(/request failed/i)).toBeInTheDocument();
    });
  });

  it('shows generic error when forgotPassword rejects with a non-Error value', async () => {
    vi.spyOn(api, 'forgotPassword').mockRejectedValueOnce('string rejection');

    renderForgotPassword();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email address/i), 'test@example.com');
    await user.click(screen.getByRole('button', { name: /send reset link/i }));

    await waitFor(() => {
      expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    });
  });

  it('has link back to login', () => {
    renderForgotPassword();

    const link = screen.getByText(/back to login/i).closest('a');
    expect(link).toHaveAttribute('href', '/login');
  });
});
