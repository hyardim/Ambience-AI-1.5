import { describe, it, expect } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Routes, Route } from 'react-router-dom';
import { renderWithProviders, seedAuth } from '../test/utils';
import { NotificationDropdown } from './NotificationDropdown';

function renderDropdown(userRole: 'gp' | 'specialist' | 'admin' = 'gp') {
  seedAuth({ role: userRole });
  return renderWithProviders(
    <Routes>
      <Route path="*" element={<NotificationDropdown userRole={userRole} />} />
      <Route path="/gp/query/:queryId" element={<div>GP Query Detail</div>} />
      <Route path="/specialist/query/:queryId" element={<div>Specialist Query Detail</div>} />
    </Routes>,
    { routes: ['/'] },
  );
}

describe('NotificationDropdown', () => {
  it('renders the bell icon button', async () => {
    renderDropdown();

    await waitFor(() => {
      // The button should exist
      expect(screen.getByRole('button')).toBeInTheDocument();
    });
  });

  it('shows unread count badge', async () => {
    renderDropdown();

    await waitFor(() => {
      // We have 1 unread notification in our mock data
      expect(screen.getByText('1')).toBeInTheDocument();
    });
  });

  it('opens dropdown when bell is clicked', async () => {
    renderDropdown();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole('button')).toBeInTheDocument();
    });

    // Click the bell button (first button)
    const buttons = screen.getAllByRole('button');
    await user.click(buttons[0]);

    expect(screen.getByText('Notifications')).toBeInTheDocument();
    expect(screen.getByText('Chat assigned')).toBeInTheDocument();
    expect(screen.getByText('Chat approved')).toBeInTheDocument();
  });

  it('shows "Mark all read" button when there are unread notifications', async () => {
    renderDropdown();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('1')).toBeInTheDocument();
    });

    const buttons = screen.getAllByRole('button');
    await user.click(buttons[0]);

    expect(screen.getByText('Mark all read')).toBeInTheDocument();
  });
});
