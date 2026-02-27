import { describe, it, expect } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Routes, Route } from 'react-router-dom';
import { server } from '../../test/mocks/server';
import { renderWithProviders } from '../../test/utils';
import { RegisterPage } from './RegisterPage';

function GPStub() {
  return <div>GP Page</div>;
}
function SpecialistStub() {
  return <div>Specialist Page</div>;
}
function LoginStub() {
  return <div>Login Page</div>;
}

function renderRegister() {
  return renderWithProviders(
    <Routes>
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/gp/queries" element={<GPStub />} />
      <Route path="/specialist/queries" element={<SpecialistStub />} />
      <Route path="/login" element={<LoginStub />} />
    </Routes>,
    { routes: ['/register'] },
  );
}

describe('RegisterPage', () => {
  it('renders the registration form', async () => {
    renderRegister();

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /create your account/i })).toBeInTheDocument();
    });

    expect(screen.getByLabelText(/first name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/last name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/email address/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/confirm password/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/role/i)).toBeInTheDocument();
  });

  it('shows error when passwords do not match', async () => {
    renderRegister();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /create account/i })).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/first name/i), 'John');
    await user.type(screen.getByLabelText(/last name/i), 'Doe');
    await user.type(screen.getByLabelText(/email address/i), 'john@example.com');
    await user.type(screen.getByLabelText(/^password$/i), 'password1');
    await user.type(screen.getByLabelText(/confirm password/i), 'password2');
    await user.click(screen.getByRole('button', { name: /create account/i }));

    expect(screen.getByText(/passwords do not match/i)).toBeInTheDocument();
  });

  it('shows specialty field when specialist role is selected', async () => {
    renderRegister();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByLabelText(/role/i)).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByLabelText(/role/i), 'specialist');

    expect(screen.getByLabelText(/specialty/i)).toBeInTheDocument();
  });

  it('shows error when specialist has no specialty selected', async () => {
    renderRegister();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByLabelText(/role/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/first name/i), 'Jane');
    await user.type(screen.getByLabelText(/last name/i), 'Smith');
    await user.type(screen.getByLabelText(/email address/i), 'jane@example.com');
    await user.selectOptions(screen.getByLabelText(/role/i), 'specialist');
    await user.type(screen.getByLabelText(/^password$/i), 'pass123');
    await user.type(screen.getByLabelText(/confirm password/i), 'pass123');
    await user.click(screen.getByRole('button', { name: /create account/i }));

    expect(screen.getByText(/please select a specialty/i)).toBeInTheDocument();
  });

  it('registers successfully and navigates to GP page', async () => {
    renderRegister();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /create account/i })).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/first name/i), 'John');
    await user.type(screen.getByLabelText(/last name/i), 'Doe');
    await user.type(screen.getByLabelText(/email address/i), 'john@example.com');
    await user.type(screen.getByLabelText(/^password$/i), 'password123');
    await user.type(screen.getByLabelText(/confirm password/i), 'password123');
    await user.click(screen.getByRole('button', { name: /create account/i }));

    await waitFor(() => {
      expect(screen.getByText('GP Page')).toBeInTheDocument();
    });
  });

  it('shows API error on registration failure', async () => {
    server.use(
      http.post('/auth/register', () => {
        return HttpResponse.json({ detail: 'Email already exists' }, { status: 400 });
      }),
    );

    renderRegister();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /create account/i })).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/first name/i), 'John');
    await user.type(screen.getByLabelText(/last name/i), 'Doe');
    await user.type(screen.getByLabelText(/email address/i), 'existing@example.com');
    await user.type(screen.getByLabelText(/^password$/i), 'password123');
    await user.type(screen.getByLabelText(/confirm password/i), 'password123');
    await user.click(screen.getByRole('button', { name: /create account/i }));

    await waitFor(() => {
      expect(screen.getByText('Email already exists')).toBeInTheDocument();
    });
  });

  it('has link to login page', async () => {
    renderRegister();

    await waitFor(() => {
      expect(screen.getByText(/login here/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/login here/i).closest('a')).toHaveAttribute('href', '/login');
  });

  it('toggles password visibility', async () => {
    renderRegister();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument();
    });

    const passwordInput = screen.getByLabelText(/^password$/i);
    expect(passwordInput).toHaveAttribute('type', 'password');

    const toggleButton = passwordInput.parentElement!.querySelector('button')!;
    await user.click(toggleButton);

    expect(passwordInput).toHaveAttribute('type', 'text');
  });
});
