import { describe, it, expect, vi } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Routes, Route } from 'react-router-dom';
import { server } from '@test/mocks/server';
import { renderWithProviders } from '@test/utils';
import { ResendVerificationPage } from '@/pages/auth/ResendVerificationPage';
import * as api from '@/services/api';

function LoginStub() {
  return <div>Login Page</div>;
}

function renderResendVerification(route = '/resend-verification') {
  return renderWithProviders(
    <Routes>
      <Route path="/resend-verification" element={<ResendVerificationPage />} />
      <Route path="/login" element={<LoginStub />} />
    </Routes>,
    { routes: [route] },
  );
}

describe('ResendVerificationPage', () => {
  it('renders the form', async () => {
    renderResendVerification();

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /resend verification email/i })).toBeInTheDocument();
    });

    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /resend verification email/i })).toBeInTheDocument();
  });

  it('pre-fills email from query params', () => {
    renderResendVerification('/resend-verification?email=prefilled%40example.com');

    expect(screen.getByLabelText(/email address/i)).toHaveValue('prefilled@example.com');
  });

  it('shows error when submitting empty email', async () => {
    renderResendVerification();

    const form = screen.getByRole('button', { name: /resend verification email/i }).closest('form')!;
    fireEvent.submit(form);

    expect(screen.getByText(/email is required/i)).toBeInTheDocument();
  });

  it('calls resendVerificationEmail API on submit and shows success message', async () => {
    renderResendVerification();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email address/i), 'test@example.com');
    await user.click(screen.getByRole('button', { name: /resend verification email/i }));

    await waitFor(() => {
      expect(screen.getByText(/verification link will be sent/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/back to login/i)).toBeInTheDocument();
  });

  it('shows error on API failure', async () => {
    server.use(
      http.post('/auth/resend-verification', () =>
        HttpResponse.json({ detail: 'Too many requests' }, { status: 429 })),
    );

    renderResendVerification();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email address/i), 'test@example.com');
    await user.click(screen.getByRole('button', { name: /resend verification email/i }));

    await waitFor(() => {
      expect(screen.getByText(/too many requests/i)).toBeInTheDocument();
    });
  });

  it('shows fallback error for non-Error exceptions', async () => {
    server.use(
      http.post('/auth/resend-verification', () =>
        new HttpResponse(null, { status: 500 })),
    );

    renderResendVerification();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email address/i), 'test@example.com');
    await user.click(screen.getByRole('button', { name: /resend verification email/i }));

    await waitFor(() => {
      expect(screen.getByText(/request failed/i)).toBeInTheDocument();
    });
  });

  it('shows generic error when resendVerificationEmail rejects with a non-Error value', async () => {
    vi.spyOn(api, 'resendVerificationEmail').mockRejectedValueOnce('string rejection');

    renderResendVerification();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email address/i), 'test@example.com');
    await user.click(screen.getByRole('button', { name: /resend verification email/i }));

    await waitFor(() => {
      expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
    });
  });

  it('has link back to login', () => {
    renderResendVerification();

    const links = screen.getAllByText(/back to login/i);
    expect(links[0].closest('a')).toHaveAttribute('href', '/login');
  });
});
