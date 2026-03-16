import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { AuthHeader } from '@/components/AuthHeader';
import { renderWithProviders } from '@test/utils';

describe('AuthHeader', () => {
  it('renders login and register links', () => {
    renderWithProviders(<AuthHeader />, { withAuth: false });

    expect(screen.getByRole('link', { name: 'Login' })).toHaveAttribute('href', '/login');
    expect(screen.getByRole('link', { name: 'Register' })).toHaveAttribute('href', '/register');
  });
});
