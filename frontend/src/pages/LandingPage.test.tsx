import { describe, it, expect } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LandingPage } from './LandingPage';
import { renderWithProviders, seedAuth } from '../test/utils';

describe('LandingPage', () => {
  it('shows public auth links for anonymous users', async () => {
    renderWithProviders(<LandingPage />, { routes: ['/'] });

    await waitFor(() => {
      expect(screen.getByText(/NHS Ambience AI 1.5/i)).toBeInTheDocument();
    });

    expect(screen.getByRole('link', { name: 'Login' })).toHaveAttribute('href', '/login');
    expect(screen.getByRole('link', { name: 'Register' })).toHaveAttribute('href', '/register');
  });

  it('shows admin portal and allows logout when authenticated as admin', async () => {
    seedAuth({ role: 'admin', username: 'Admin User' });
    renderWithProviders(<LandingPage />, { routes: ['/'] });

    await waitFor(() => {
      expect(screen.getByText(/signed in as/i)).toBeInTheDocument();
    });

    expect(screen.getByRole('heading', { name: 'Admin Panel' })).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /logout/i }));

    await waitFor(() => {
      expect(screen.getByRole('link', { name: 'Login' })).toBeInTheDocument();
    });
  });
});
