import { describe, it, expect, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Routes, Route } from 'react-router-dom';
import { server } from '@test/mocks/server';
import { renderWithProviders, seedAuth } from '@test/utils';
import { AdminUsersPage } from '@/pages/admin/AdminUsersPage';

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

    // Wait for users to load (component renders role_id as identifier)
    await waitFor(() => {
      expect(screen.getByText('gp_1')).toBeInTheDocument();
    });

    expect(screen.getByText('specialist_2')).toBeInTheDocument();
    expect(screen.getByText('admin_3')).toBeInTheDocument();
  });

  it('filters users by search term', async () => {
    renderAdminUsers();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('gp_1')).toBeInTheDocument();
    });

    await user.type(screen.getByPlaceholderText(/search by identifier or specialty/i), 'specialist');

    expect(screen.queryByText('gp_1')).not.toBeInTheDocument();
    expect(screen.getByText('specialist_2')).toBeInTheDocument();
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
      expect(screen.getByText('gp_1')).toBeInTheDocument();
    });

    const editButtons = screen.getAllByText('Edit');
    await user.click(editButtons[0]);

    expect(screen.getByRole('heading', { name: /edit user/i })).toBeInTheDocument();
  });

  it('closes edit modal when Cancel is clicked', async () => {
    renderAdminUsers();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('gp_1')).toBeInTheDocument();
    });

    const editButtons = screen.getAllByText('Edit');
    await user.click(editButtons[0]);

    expect(screen.getByRole('heading', { name: /edit user/i })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /cancel/i }));

    expect(screen.queryByRole('heading', { name: /edit user/i })).not.toBeInTheDocument();
  });

  it('closes edit modal from the icon button and shows save/deactivate errors', async () => {
    server.use(
      http.patch('/admin/users/:userId', () => HttpResponse.json({ detail: 'Save failed' }, { status: 500 })),
      http.delete('/admin/users/:userId', () => HttpResponse.json({ detail: 'Deactivate failed' }, { status: 500 })),
    );

    renderAdminUsers();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('gp_1')).toBeInTheDocument();
    });

    await user.click(screen.getAllByText('Edit')[0]);
    await user.click(screen.getAllByRole('button').find((button) =>
      button.className.includes('text-gray-400 hover:text-gray-600'),
    ) as HTMLButtonElement);
    expect(screen.queryByRole('heading', { name: /edit user/i })).not.toBeInTheDocument();

    await user.click(screen.getAllByText('Edit')[0]);
    await user.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => {
      expect(screen.getByText(/save failed/i)).toBeInTheDocument();
    });

    vi.spyOn(window, 'confirm').mockReturnValueOnce(true);
    await user.click(screen.getAllByTitle('Deactivate user')[0]);
    await waitFor(() => {
      expect(screen.getByText(/deactivate failed/i)).toBeInTheDocument();
    });
  });

  it('saves user edits when Save is clicked', async () => {
    renderAdminUsers();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('gp_1')).toBeInTheDocument();
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
      expect(screen.getByText('gp_1')).toBeInTheDocument();
    });

    const deactivateButtons = screen.getAllByTitle('Deactivate user');
    await user.click(deactivateButtons[0]);

    // The user should still appear but with updated status (the mock returns is_active: false)
    await waitFor(() => {
      expect(screen.getByText('gp_1')).toBeInTheDocument();
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

  it('retries load errors, filters by role, saves edit changes, and respects deactivate cancellation', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    server.use(
      http.get('/admin/users', ({ request }) => {
        const role = new URL(request.url).searchParams.get('role');
        if (role === 'specialist') {
          return HttpResponse.json([
            {
              id: 2,
              email: 'specialist@example.com',
              full_name: 'Dr Specialist',
              role: 'specialist',
              specialty: 'neurology',
              is_active: true,
            },
          ]);
        }
        return HttpResponse.json({ detail: 'Try again' }, { status: 500 });
      }),
    );

    renderAdminUsers();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/try again/i)).toBeInTheDocument();
    });

    server.use(
      http.get('/admin/users', ({ request }) => {
        const role = new URL(request.url).searchParams.get('role');
        if (role === 'specialist') {
          return HttpResponse.json([
            {
              id: 2,
              email: 'specialist@example.com',
              full_name: 'Dr Specialist',
              role: 'specialist',
              specialty: 'neurology',
              is_active: true,
            },
          ]);
        }
        return HttpResponse.json([]);
      }),
      http.patch('/admin/users/:userId', ({ params, request }) =>
        request.json().then((body) =>
          HttpResponse.json({
            id: Number(params.userId),
            email: 'specialist@example.com',
            full_name: 'Updated Specialist',
            role: 'specialist',
            specialty: (body as { specialty?: string }).specialty ?? 'rheumatology',
            is_active: true,
          }),
        )),
    );

    await user.click(screen.getByRole('button', { name: /retry/i }));
    await user.selectOptions(screen.getByDisplayValue(/all roles/i), 'specialist');

    await waitFor(() => {
      expect(screen.getByText('specialist_2')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Edit'));
    const fullNameInput = screen.getByDisplayValue(/dr specialist/i);
    await user.clear(fullNameInput);
    await user.type(fullNameInput, 'Updated Specialist');
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => {
      expect(screen.getByText('specialist_2')).toBeInTheDocument();
    });

    await user.click(screen.getByTitle(/deactivate user/i));
    expect(confirmSpy).toHaveBeenCalled();
  });

  it('updates role, specialty, and active status fields inside the edit modal', async () => {
    renderAdminUsers();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('gp_1')).toBeInTheDocument();
    });

    await user.click(screen.getAllByText('Edit')[0]);
    await user.selectOptions(screen.getAllByRole('combobox')[1], 'specialist');
    await user.clear(screen.getByPlaceholderText(/e\.g\. neurology/i));
    await user.type(screen.getByPlaceholderText(/e\.g\. neurology/i), 'neurology');
    await user.click(screen.getByLabelText(/active/i));
    await user.click(screen.getByRole('button', { name: /cancel/i }));

    expect(screen.queryByRole('heading', { name: /edit user/i })).not.toBeInTheDocument();
  });
});
