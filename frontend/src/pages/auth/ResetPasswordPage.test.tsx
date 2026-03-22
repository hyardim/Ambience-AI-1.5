import { describe, it, expect } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Routes, Route } from 'react-router-dom';
import { renderWithProviders } from '../../test/utils';
import { server } from '../../test/mocks/server';
import { ResetPasswordPage } from './ResetPasswordPage';

const API = 'http://localhost:8000';

function LoginStub() {
  return <div>Login Page</div>;
}

function ForgotStub() {
  return <div>Forgot Password Page</div>;
}

function renderReset(route = '/reset-password?token=test-token') {
  return renderWithProviders(
    <Routes>
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/login" element={<LoginStub />} />
      <Route path="/forgot-password" element={<ForgotStub />} />
    </Routes>,
    { routes: [route] },
  );
}

describe('ResetPasswordPage', () => {
  it('shows warning when token is missing', async () => {
    renderReset('/reset-password');

    expect(screen.getByText(/this reset link is incomplete/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reset password/i })).toBeDisabled();
  });

  it('validates password confirmation mismatch', async () => {
    renderReset();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/^new password$/i), 'NewSecure1!');
    await user.type(screen.getByLabelText(/confirm new password/i), 'Different1!');
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    expect(screen.getByText(/passwords do not match/i)).toBeInTheDocument();
  });

  it('resets password successfully with valid token', async () => {
    renderReset();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/^new password$/i), 'NewSecure1!');
    await user.type(screen.getByLabelText(/confirm new password/i), 'NewSecure1!');
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    await waitFor(() => {
      expect(screen.getByText(/your password has been reset/i)).toBeInTheDocument();
    });
  });

  it('shows safe invalid-token error message', async () => {
    server.use(
      http.post(`${API}/auth/reset-password/confirm`, () => {
        return HttpResponse.json({ detail: 'Invalid or expired reset token' }, { status: 400 });
      }),
    );

    renderReset('/reset-password?token=bad-token');
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/^new password$/i), 'NewSecure1!');
    await user.type(screen.getByLabelText(/confirm new password/i), 'NewSecure1!');
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    await waitFor(() => {
      expect(screen.getByText(/invalid or expired reset token/i)).toBeInTheDocument();
    });
  });
});
