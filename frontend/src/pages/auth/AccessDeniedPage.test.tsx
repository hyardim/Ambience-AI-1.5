import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Routes, Route } from 'react-router-dom';
import { renderWithProviders, seedAuth } from '../../test/utils';
import { AccessDeniedPage } from './AccessDeniedPage';

function renderAccessDenied() {
  return renderWithProviders(
    <Routes>
      <Route path="/access-denied" element={<AccessDeniedPage />} />
      <Route path="/" element={<div>Home</div>} />
    </Routes>,
    {
      routes: [{
        pathname: '/access-denied',
        state: { from: 'Admin area', currentRole: 'gp', requiredRoles: ['admin'] },
      }],
    },
  );
}

describe('AccessDeniedPage', () => {
  it('renders role information from route state', () => {
    seedAuth({ role: 'gp' });
    renderAccessDenied();

    expect(screen.getByText(/Access Restricted/i)).toBeInTheDocument();
    expect(screen.getByText(/Admin area/i)).toBeInTheDocument();
    expect(screen.getByText(/Your role:/i)).toBeInTheDocument();
    expect(screen.getByText(/Required role\(s\):/i)).toBeInTheDocument();
  });

  it('switch account logs user out', async () => {
    seedAuth({ role: 'gp' });
    renderAccessDenied();

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /Switch Account/i }));

    expect(localStorage.getItem('access_token')).toBeNull();
  });
});
