import { describe, it, expect } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Routes, Route } from 'react-router-dom';

import { renderWithProviders } from '../../test/utils';
import { ResendVerificationPage } from './ResendVerificationPage';

function LoginStub() {
  return <div>Login Page</div>;
}

function renderResend(route = '/resend-verification') {
  return renderWithProviders(
    <Routes>
      <Route path="/resend-verification" element={<ResendVerificationPage />} />
      <Route path="/login" element={<LoginStub />} />
    </Routes>,
    { routes: [route] },
  );
}

describe('ResendVerificationPage', () => {
  it('prefills email from query string', () => {
    renderResend('/resend-verification?email=gp%40example.com');
    expect(screen.getByLabelText(/email address/i)).toHaveValue('gp@example.com');
  });

  it('submits and shows generic success message', async () => {
    renderResend();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email address/i), 'gp@example.com');
    await user.click(screen.getByRole('button', { name: /resend verification email/i }));

    await waitFor(() => {
      expect(screen.getByText(/if an account exists and requires verification/i)).toBeInTheDocument();
    });
  });

  it('validates missing email', async () => {
    renderResend();
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: /resend verification email/i }));

    expect(screen.getByText(/email is required/i)).toBeInTheDocument();
  });
});
