import { describe, it, expect } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { Routes, Route } from 'react-router-dom';

import { server } from '../../test/mocks/server';
import { renderWithProviders } from '../../test/utils';
import { VerifyEmailPage } from './VerifyEmailPage';

const API = 'http://localhost:8000';

function LoginStub() {
  return <div>Login Page</div>;
}

function ResendStub() {
  return <div>Resend Verification Page</div>;
}

function renderVerify(route = '/verify-email?token=test-token') {
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
  it('shows error when token is missing', async () => {
    renderVerify('/verify-email');

    await waitFor(() => {
      expect(screen.getByText(/verification token is missing/i)).toBeInTheDocument();
    });
  });

  it('shows success message for valid token', async () => {
    renderVerify('/verify-email?token=ok-token');

    await waitFor(() => {
      expect(screen.getByText(/email verified successfully/i)).toBeInTheDocument();
    });
  });

  it('shows invalid token error state', async () => {
    server.use(
      http.post(`${API}/auth/verify-email/confirm`, () => {
        return HttpResponse.json({ detail: 'Invalid or expired verification token' }, { status: 400 });
      }),
    );

    renderVerify('/verify-email?token=bad-token');

    await waitFor(() => {
      expect(screen.getByText(/invalid or expired verification token/i)).toBeInTheDocument();
    });
  });
});
