import { describe, it, expect } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Routes, Route } from 'react-router-dom';
import { ResetPasswordPage } from '@/pages/auth/ResetPasswordPage';
import { renderWithProviders } from '@test/utils';
import { server } from '@test/mocks/server';

function renderReset(route = '/reset-password?token=test-reset-token') {
  return renderWithProviders(
    <Routes>
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/login" element={<div>Login Page</div>} />
      <Route path="/forgot-password" element={<div>Forgot Password Page</div>} />
    </Routes>,
    { routes: [route] },
  );
}

describe('ResetPasswordPage', () => {
  it('shows validation errors for missing fields and mismatched passwords', async () => {
    renderReset();
    const user = userEvent.setup();
    const form = screen.getByRole('button', { name: /reset password/i }).closest('form')!;

    fireEvent.submit(form);
    expect(screen.getByText(/all fields are required/i)).toBeInTheDocument();

    await user.type(screen.getByLabelText(/^New password$/i), 'Password1!');
    await user.type(screen.getByLabelText(/^Confirm new password$/i), 'Password2!');
    fireEvent.submit(form);

    expect(screen.getByText(/passwords do not match/i)).toBeInTheDocument();
  });

  it('toggles password visibility and completes reset flow', async () => {
    renderReset();
    const user = userEvent.setup();

    const passwordInput = screen.getByLabelText(/^New password$/i);
    expect(passwordInput).toHaveAttribute('type', 'password');
    await user.click(passwordInput.parentElement!.querySelector('button')!);
    expect(passwordInput).toHaveAttribute('type', 'text');

    await user.type(screen.getByLabelText(/^New password$/i), 'Password1!');
    await user.type(screen.getByLabelText(/^Confirm new password$/i), 'Password1!');
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    await waitFor(() => {
      expect(screen.getByText(/your password has been reset/i)).toBeInTheDocument();
    });
  });

  it('shows error when token is missing and submit is attempted', async () => {
    renderReset('/reset-password');

    const form = screen.getByRole('button', { name: /reset password/i }).closest('form')!;
    fireEvent.submit(form);

    expect(screen.getByText(/reset token is missing/i)).toBeInTheDocument();
    expect(screen.getByText(/this reset link is incomplete/i)).toBeInTheDocument();
  });

  it('shows API errors', async () => {
    server.use(
      http.post('/auth/reset-password/confirm', () =>
        HttpResponse.json({ detail: 'Reset failed' }, { status: 400 })),
    );

    renderReset();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/^New password$/i), 'Password1!');
    await user.type(screen.getByLabelText(/^Confirm new password$/i), 'Password1!');
    await user.click(screen.getByRole('button', { name: /reset password/i }));

    await waitFor(() => {
      expect(screen.getByText(/reset failed/i)).toBeInTheDocument();
    });
  });
});
