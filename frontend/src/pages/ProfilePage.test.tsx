import { describe, it, expect } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Routes, Route } from 'react-router-dom';
import { renderWithProviders, seedAuth } from '../test/utils';
import { ProfilePage } from './ProfilePage';

function renderProfile() {
  seedAuth({ role: 'gp', username: 'Dr GP' });
  return renderWithProviders(
    <Routes>
      <Route path="/profile" element={<ProfilePage />} />
      <Route path="/gp/queries" element={<div>GP Queries</div>} />
    </Routes>,
    { routes: ['/profile'] },
  );
}

describe('ProfilePage', () => {
  it('loads and displays profile data', async () => {
    renderProfile();

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /My Profile/i })).toBeInTheDocument();
    });

    expect(screen.getByText('gp@example.com')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Save Changes/i })).toBeInTheDocument();
  });

  it('shows validation when new password lacks current password', async () => {
    renderProfile();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByLabelText(/^New Password$/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/^New Password$/i), 'NewPass123!');
    await user.type(screen.getByLabelText(/Confirm New Password/i), 'NewPass123!');
    await user.click(screen.getByRole('button', { name: /Save Changes/i }));

    expect(screen.getByText(/Current password is required/i)).toBeInTheDocument();
  });
});
