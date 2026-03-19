import { describe, it, expect } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Routes, Route } from 'react-router-dom';
import { renderWithProviders } from '../../test/utils';
import { ForgotPasswordPage } from './ForgotPasswordPage';

function LoginStub() {
  return <div>Login Page</div>;
}

function renderForgot(route = '/forgot-password') {
  return renderWithProviders(
    <Routes>
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/login" element={<LoginStub />} />
    </Routes>,
    { routes: [route] },
  );
}

describe('ForgotPasswordPage', () => {
  it('submits email and shows generic success message', async () => {
    renderForgot();
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/email address/i), 'gp@example.com');
    await user.click(screen.getByRole('button', { name: /send reset link/i }));

    await waitFor(() => {
      expect(screen.getByText(/if that email is registered/i)).toBeInTheDocument();
    });
  });

  it('shows validation error when email is missing', async () => {
    renderForgot();
    const user = userEvent.setup();

    await user.click(screen.getByRole('button', { name: /send reset link/i }));

    expect(screen.getByText(/email is required/i)).toBeInTheDocument();
  });
});
