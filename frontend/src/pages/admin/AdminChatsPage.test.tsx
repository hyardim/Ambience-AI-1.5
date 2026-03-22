import { describe, it, expect, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { server } from '../../test/mocks/server';
import { renderWithProviders, seedAuth } from '../../test/utils';
import { AdminChatsPage } from './AdminChatsPage';

const API = 'http://localhost:8000';

describe('AdminChatsPage', () => {
  it('renders chats and supports search filtering', async () => {
    seedAuth({ role: 'admin', username: 'Admin User' });
    renderWithProviders(<AdminChatsPage />, { routes: ['/admin/chats'] });

    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.type(screen.getByPlaceholderText(/Search by title or owner/i), 'nothing');

    expect(screen.getByText(/No chats found/i)).toBeInTheDocument();
  });

  it('opens detail modal', async () => {
    seedAuth({ role: 'admin', username: 'Admin User' });
    renderWithProviders(<AdminChatsPage />, { routes: ['/admin/chats'] });

    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByTitle('View messages'));

    await waitFor(() => {
      expect(screen.getByText(/Patient has a headache/i)).toBeInTheDocument();
    });
  });

  it('deletes a chat when confirmed', async () => {
    seedAuth({ role: 'admin', username: 'Admin User' });
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);

    server.use(
      http.delete(`${API}/admin/chats/:chatId`, () => new HttpResponse(null, { status: 204 })),
    );

    renderWithProviders(<AdminChatsPage />, { routes: ['/admin/chats'] });
    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByTitle('Delete chat'));

    await waitFor(() => {
      expect(screen.queryByText('Headache consultation')).not.toBeInTheDocument();
    });

    confirmSpy.mockRestore();
  });
});
