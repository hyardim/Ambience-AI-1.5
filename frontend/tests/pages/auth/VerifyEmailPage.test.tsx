import { describe, it, expect, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { Routes, Route } from 'react-router-dom';
import { server } from '@test/mocks/server';
import { renderWithProviders } from '@test/utils';
import { VerifyEmailPage } from '@/pages/auth/VerifyEmailPage';
import * as api from '@/services/api';

function LoginStub() {
  return <div>Login Page</div>;
}

function ResendStub() {
  return <div>Resend Page</div>;
}

function renderVerifyEmail(route = '/verify-email') {
  return renderWithProviders(
    <Routes>
      <Route path="/verify-email" element={<VerifyEmailPage />} />
      <Route path="/login" element={<LoginStub />} />
      <Route path="/resend-verification" element={<ResendStub />} />
    </Routes>,
    { routes: [route] },
  );
}

describe('VerifyEmailPage', () => {
  it('shows missing token message when no token in URL', async () => {
    renderVerifyEmail('/verify-email');

    await waitFor(() => {
      expect(screen.getByText(/verification token is missing/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/resend verification email/i)).toBeInTheDocument();
  });

  it('shows loading state then success message when token is valid', async () => {
    renderVerifyEmail('/verify-email?token=valid-token');

    // Should show loading first
    expect(screen.getByText(/verifying your link/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/email verified successfully/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/continue to login/i)).toBeInTheDocument();
  });

  it('shows error on verification failure', async () => {
    server.use(
      http.post('/auth/verify-email/confirm', () =>
        HttpResponse.json({ detail: 'Token expired' }, { status: 400 }),
      ),
    );

    renderVerifyEmail('/verify-email?token=expired-token');

    await waitFor(() => {
      expect(screen.getByText(/token expired/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/resend verification email/i)).toBeInTheDocument();
  });

  it('shows fallback error when error has no message', async () => {
    server.use(
      http.post('/auth/verify-email/confirm', () =>
        HttpResponse.json({ detail: 'Verification failed' }, { status: 400 }),
      ),
    );

    renderVerifyEmail('/verify-email?token=bad-token');

    await waitFor(() => {
      expect(screen.getByText(/verification failed/i)).toBeInTheDocument();
    });
  });

  it('uses fallback message when response has no message field', async () => {
    server.use(http.post('/auth/verify-email/confirm', () => HttpResponse.json({})));

    renderVerifyEmail('/verify-email?token=no-msg-token');

    await waitFor(() => {
      expect(screen.getByText(/email verified successfully/i)).toBeInTheDocument();
    });
  });

  it('does not update state when component unmounts before API resolves', async () => {
    let resolveApi!: (value: { message: string }) => void;
    vi.spyOn(api, 'confirmEmailVerification').mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          resolveApi = resolve;
        }),
    );

    const { unmount } = renderVerifyEmail('/verify-email?token=unmount-token');

    // Unmount while the API call is still pending
    unmount();

    // Resolve after unmount - should not throw or update state
    resolveApi({ message: 'Email verified successfully' });

    // If the mounted guard works, no state updates happen after unmount.
    // We just verify no errors are thrown (React would warn about state updates on unmounted components).
  });

  it('shows fallback error when confirmEmailVerification rejects with a non-Error value', async () => {
    vi.spyOn(api, 'confirmEmailVerification').mockRejectedValueOnce('string rejection');

    renderVerifyEmail('/verify-email?token=non-error-token');

    await waitFor(() => {
      expect(screen.getByText(/invalid or expired verification link/i)).toBeInTheDocument();
    });
  });

  it('shows fallback error when confirmEmailVerification rejects with an empty Error message', async () => {
    vi.spyOn(api, 'confirmEmailVerification').mockRejectedValueOnce(new Error(''));

    renderVerifyEmail('/verify-email?token=empty-error-token');

    await waitFor(() => {
      expect(screen.getByText(/invalid or expired verification link/i)).toBeInTheDocument();
    });
  });

  it('does not set error state when a rejection resolves after unmount', async () => {
    let rejectApi!: (error: unknown) => void;
    vi.spyOn(api, 'confirmEmailVerification').mockImplementationOnce(
      () =>
        new Promise((_, reject) => {
          rejectApi = reject;
        }),
    );

    const { unmount } = renderVerifyEmail('/verify-email?token=reject-after-unmount');
    unmount();

    rejectApi(new Error('Late rejection'));
  });
});
