import { describe, it, expect } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Routes, Route } from 'react-router-dom';
import { server } from '../../test/mocks/server';
import { renderWithProviders, seedAuth } from '../../test/utils';
import { AdminUsersPage } from './AdminUsersPage';

function renderAdminUsers() {
  seedAuth({ role: 'admin', username: 'Admin User' });
  return renderWithProviders(
    <Routes>
      <Route path="/admin/users" element={<AdminUsersPage />} />
      <Route path="/admin/chats" element={<div>Admin Chats</div>} />
      <Route path="/admin/logs" element={<div>Admin Logs</div>} />
      <Route path="/profile" element={<div>Profile</div>} />
      <Route path="/login" element={<div>Login</div>} />
    </Routes>,
    { routes: ['/admin/users'] },
  );
}

describe('AdminUsersPage', () => {
  it('renders the user management page with users', async () => {
    renderAdminUsers();

    await waitFor(() => {
      expect(screen.getByText('User Management')).toBeInTheDocument();
    });

    // Wait for users to load
    await waitFor(() => {
      expect(screen.getByText('gp@example.com')).toBeInTheDocument();
    });

    expect(screen.getByText('specialist@example.com')).toBeInTheDocument();
    expect(screen.getByText('admin@example.com')).toBeInTheDocument();
  });

  it('filters users by search term', async () => {
    renderAdminUsers();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('gp@example.com')).toBeInTheDocument();
    });

    await user.type(screen.getByPlaceholderText(/search by name or email/i), 'specialist');

    expect(screen.queryByText('gp@example.com')).not.toBeInTheDocument();
    expect(screen.getByText('specialist@example.com')).toBeInTheDocument();
  });

  it('shows error message on load failure', async () => {
    server.use(
      http.get('/admin/users', () => {
        return HttpResponse.json({ detail: 'Forbidden' }, { status: 403 });
      }),
    );

    renderAdminUsers();

    await waitFor(() => {
      expect(screen.getByText('Forbidden')).toBeInTheDocument();
    });
  });

  it('opens edit modal when Edit button is clicked', async () => {
    renderAdminUsers();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('gp@example.com')).toBeInTheDocument();
    });

    const editButtons = screen.getAllByText('Edit');
    await user.click(editButtons[0]);

    expect(screen.getByRole('heading', { name: /edit user/i })).toBeInTheDocument();
  });

  it('closes edit modal when Cancel is clicked', async () => {
    renderAdminUsers();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('gp@example.com')).toBeInTheDocument();
    });

    const editButtons = screen.getAllByText('Edit');
    await user.click(editButtons[0]);

    expect(screen.getByRole('heading', { name: /edit user/i })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /cancel/i }));

    expect(screen.queryByRole('heading', { name: /edit user/i })).not.toBeInTheDocument();
  });

  it('saves user edits when Save is clicked', async () => {
    renderAdminUsers();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('gp@example.com')).toBeInTheDocument();
    });

    const editButtons = screen.getAllByText('Edit');
    await user.click(editButtons[0]);

    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => {
      expect(screen.queryByRole('heading', { name: /edit user/i })).not.toBeInTheDocument();
    });
  });

  it('deactivates a user when the deactivate button is clicked', async () => {
    renderAdminUsers();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('gp@example.com')).toBeInTheDocument();
    });

    const deactivateButtons = screen.getAllByTitle('Deactivate user');
    await user.click(deactivateButtons[0]);

    // The user should still appear but with updated status (the mock returns is_active: false)
    await waitFor(() => {
      expect(screen.getByText('gp@example.com')).toBeInTheDocument();
    });
  });

  it('shows no users message when list is empty', async () => {
    server.use(
      http.get('/admin/users', () => {
        return HttpResponse.json([]);
      }),
    );

    renderAdminUsers();

    await waitFor(() => {
      expect(screen.getByText('No users found.')).toBeInTheDocument();
    });
  });
});
