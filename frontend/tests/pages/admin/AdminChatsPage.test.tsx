import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Routes, Route } from 'react-router-dom';
import { AdminChatsPage } from '@/pages/admin/AdminChatsPage';
import { getAdminChatDetailMessageClass } from '@/utils/adminChats';
import { renderWithProviders, seedAuth } from '@test/utils';
import { server } from '@test/mocks/server';
import { mockAdminChats, mockChatWithMessages } from '@test/mocks/handlers';

function renderPage() {
  seedAuth({ role: 'admin', username: 'Admin' });
  return renderWithProviders(
    <Routes>
      <Route path="/admin/chats" element={<AdminChatsPage />} />
      <Route path="/login" element={<div>Login</div>} />
    </Routes>,
    { routes: ['/admin/chats'] },
  );
}

describe('AdminChatsPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders chats, filters them, opens detail, edits, and deletes', async () => {
    server.use(
      http.patch('/admin/chats/:chatId', ({ params, request }) =>
        request.json().then((body) =>
          HttpResponse.json({
            ...mockAdminChats[0],
            id: Number(params.chatId),
            ...body,
          }),
        )),
      http.delete('/admin/chats/:chatId', () => new HttpResponse(null, { status: 204 })),
    );

    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /chat management/i })).toBeInTheDocument();
    });

    expect(screen.getByText(/headache consultation/i)).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText(/search by title or owner/i), 'missing');
    expect(screen.getByText(/no chats found/i)).toBeInTheDocument();

    await user.clear(screen.getByPlaceholderText(/search by title or owner/i));
    await user.selectOptions(screen.getByDisplayValue(/all status/i), 'open');

    await waitFor(() => {
      expect(screen.getByText(/headache consultation/i)).toBeInTheDocument();
    });

    await user.click(screen.getByTitle(/view messages/i));
    await waitFor(() => {
      expect(screen.getByText(/patient has a headache/i)).toBeInTheDocument();
    });
    await user.click(screen.getAllByRole('button').find((button) =>
      button.querySelector('svg') && button.closest('[class*="fixed"]'),
    ) as HTMLButtonElement);

    await user.click(screen.getByRole('button', { name: /edit/i }));
    const titleInput = screen.getByDisplayValue(/headache consultation/i);
    await user.clear(titleInput);
    await user.type(titleInput, 'Updated consultation');
    await user.selectOptions(screen.getAllByRole('combobox')[1], 'flagged');
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => {
      expect(screen.getByText(/updated consultation/i)).toBeInTheDocument();
    });

    await user.click(screen.getByTitle(/delete chat/i));
    await user.click(screen.getByRole('button', { name: /^delete$/i }));

    await waitFor(() => {
      expect(screen.queryByText(/updated consultation/i)).not.toBeInTheDocument();
    });
  }, 15000);

  it('shows error states and retries', async () => {
    server.use(
      http.get('/admin/chats', () => HttpResponse.json({ detail: 'No chats' }, { status: 500 })),
    );
    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/^No chats$/i)).toBeInTheDocument();
    });

    server.use(http.get('/admin/chats', () => HttpResponse.json(mockAdminChats)));
    await user.click(screen.getByRole('button', { name: /retry/i }));

    await waitFor(() => {
      expect(screen.getByText(/headache consultation/i)).toBeInTheDocument();
    });
  });

  it('shows detail and update errors and respects delete cancellation', async () => {
    server.use(
      http.get('/admin/chats/:chatId', () =>
        HttpResponse.json({ detail: 'Detail failed' }, { status: 500 })),
      http.patch('/admin/chats/:chatId', () =>
        HttpResponse.json({ detail: 'Update failed' }, { status: 500 })),
    );

    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/headache consultation/i)).toBeInTheDocument();
    });

    await user.click(screen.getByTitle(/view messages/i));
    await waitFor(() => {
      expect(screen.getByText(/detail failed/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /edit/i }));
    await user.click(screen.getByRole('button', { name: /save changes/i }));
    await waitFor(() => {
      expect(screen.getByText(/update failed/i)).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /cancel/i }));

    await user.click(screen.getByTitle(/delete chat/i));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /cancel/i }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(screen.getByText(/headache consultation/i)).toBeInTheDocument();
  });

  it('lets admins edit specialty and severity, close the modal from the icon button, and surfaces delete errors', async () => {
    server.use(
      http.patch('/admin/chats/:chatId', ({ params, request }) =>
        request.json().then((body) =>
          HttpResponse.json({
            ...mockAdminChats[0],
            id: Number(params.chatId),
            ...body,
          }),
        )),
      http.delete('/admin/chats/:chatId', () =>
        HttpResponse.json({ detail: 'Delete failed' }, { status: 500 })),
    );

    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/headache consultation/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /edit/i }));
    await user.clear(screen.getByPlaceholderText(/e\.g\. neurology/i));
    await user.type(screen.getByPlaceholderText(/e\.g\. neurology/i), 'rheumatology');
    await user.selectOptions(screen.getAllByRole('combobox')[2], '');
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => {
      expect(screen.queryByRole('heading', { name: /edit chat/i })).not.toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /edit/i }));
    const closeButton = screen.getAllByRole('button').find((button) =>
      button.className.includes('text-gray-400 hover:text-gray-600'),
    ) as HTMLButtonElement;
    await user.click(closeButton);
    expect(screen.queryByRole('heading', { name: /edit chat/i })).not.toBeInTheDocument();

    await user.click(screen.getByTitle(/delete chat/i));
    await user.click(screen.getByRole('button', { name: /^delete$/i }));
    await waitFor(() => {
      expect(screen.getByText(/delete failed/i)).toBeInTheDocument();
    });
  });

  it('shows empty detail state when a chat has no messages', async () => {
    server.use(
      http.get('/admin/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          messages: [],
        })),
    );

    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/headache consultation/i)).toBeInTheDocument();
    });

    await user.click(screen.getByTitle(/view messages/i));
    await waitFor(() => {
      expect(screen.getByText(/no messages in this chat/i)).toBeInTheDocument();
    });
  });

  it('returns the correct detail message class for each sender type', () => {
    expect(getAdminChatDetailMessageClass('ai')).toContain('bg-blue-50');
    expect(getAdminChatDetailMessageClass('specialist')).toContain('bg-green-50');
    expect(getAdminChatDetailMessageClass('gp')).toBe('bg-gray-50');
  });
});
