import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Routes, Route } from 'react-router-dom';
import { AccessDeniedPage } from '@/pages/auth/AccessDeniedPage';
import { renderWithProviders, seedAuth } from '@test/utils';

describe('AccessDeniedPage', () => {
  it('renders role information from router state', () => {
    seedAuth({ role: 'specialist' });
    renderWithProviders(
      <Routes>
        <Route path="/access-denied" element={<AccessDeniedPage />} />
      </Routes>,
      {
        routes: [{
          pathname: '/access-denied',
          state: {
            from: '/admin/users',
            currentRole: 'specialist',
            requiredRoles: ['admin'],
          },
        }],
      },
    );

    expect(screen.getByText(/Access Restricted/)).toBeInTheDocument();
    expect(screen.getByText(/admin\/users/i)).toBeInTheDocument();
    expect(screen.getByText(/Specialist/)).toBeInTheDocument();
    expect(screen.getByText(/Admin/)).toBeInTheDocument();
  });

  it('uses auth role fallback and logs out when switching account', async () => {
    seedAuth({ role: 'gp' });
    const user = userEvent.setup();

    renderWithProviders(
      <Routes>
        <Route path="/access-denied" element={<AccessDeniedPage />} />
        <Route path="/" element={<div>Home</div>} />
      </Routes>,
      { routes: ['/access-denied'] },
    );

    await user.click(screen.getByRole('button', { name: /switch account/i }));

    expect(localStorage.getItem('access_token')).toBeNull();
  });
});
