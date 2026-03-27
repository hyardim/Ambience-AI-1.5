import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';

import App from '@/App';
import { server } from '@test/mocks/server';
import { seedAuth } from '@test/utils';
import { mockChat, mockChat2, mockChatWithMessages, mockNotifications } from '@test/mocks/handlers';

describe('app integration flows', () => {
  it('gp consultation list renders chats', async () => {
    seedAuth({ role: 'gp', username: 'Dr GP', email: 'gp@example.com' });
    window.history.pushState({}, '', '/gp/queries');

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/my consultations/i)).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByText(mockChat2.title)).toBeInTheDocument();
    });
  });

  it('gp chat detail shows messages and citations', async () => {
    seedAuth({ role: 'gp', username: 'Dr GP', email: 'gp@example.com' });
    server.use(
      http.get('/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          messages: [
            {
              id: 1,
              content: 'Patient context',
              sender: 'user',
              created_at: '2025-01-15T10:01:00Z',
            },
            {
              id: 2,
              content: 'Grounded answer [1]',
              sender: 'ai',
              created_at: '2025-01-15T10:01:05Z',
              citations: [
                {
                  doc_id: 'doc-1',
                  title: 'NICE MS Guideline',
                  source_name: 'NICE',
                  source_url: '/docs/doc-1',
                  publish_date: '2024-01-01',
                  last_updated_date: '2024-02-01',
                },
              ],
            },
          ],
        }),
      ),
    );
    window.history.pushState({}, '', '/gp/query/1');

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/grounded answer/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/nice ms guideline/i)).toBeInTheDocument();
    expect(screen.getByText(/published 2024-01-01/i)).toBeInTheDocument();
  });

  it('gp creates new consultation', async () => {
    seedAuth({ role: 'gp', username: 'Dr GP', email: 'gp@example.com' });
    window.history.pushState({}, '', '/gp/queries/new');

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /new consultation/i })).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText(/consultation title/i), {
      target: { value: 'New MS consult' },
    });
    fireEvent.change(screen.getByLabelText(/^patient age/i), { target: { value: '42' } });
    fireEvent.change(screen.getByLabelText(/^sex/i), { target: { value: 'female' } });
    fireEvent.change(screen.getByLabelText(/specialty/i), { target: { value: 'neurology' } });
    fireEvent.change(screen.getByLabelText(/clinical question/i), {
      target: { value: 'Should we escalate DMT?' },
    });

    fireEvent.click(screen.getByRole('button', { name: /submit consultation/i }));

    await waitFor(() => {
      expect(window.location.pathname).toMatch(/^\/gp\/query\//);
    });
  });

  it('gp search filters consultations', async () => {
    seedAuth({ role: 'gp', username: 'Dr GP', email: 'gp@example.com' });
    window.history.pushState({}, '', '/gp/queries');

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(mockChat.title)).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText(/search consultations/i), {
      target: { value: 'joint pain' },
    });

    await waitFor(() => {
      expect(screen.queryByText(mockChat.title)).not.toBeInTheDocument();
    });
    expect(screen.getByText(mockChat2.title)).toBeInTheDocument();
  });

  it('specialist queue and assigned tabs', async () => {
    seedAuth({ role: 'specialist', username: 'Dr Specialist', email: 'specialist@example.com' });
    window.history.pushState({}, '', '/specialist/queries');

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /queries for review/i })).toBeInTheDocument();
    });

    expect(screen.getByText(/queue \(/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /my assigned/i }));
    expect(screen.getByText(/my assigned/i)).toBeInTheDocument();
  });

  it('specialist chat detail shows review controls', async () => {
    seedAuth({ role: 'specialist', username: 'Dr Specialist', email: 'specialist@example.com' });
    server.use(
      http.get('/specialist/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          status: 'assigned',
          specialist_id: 2,
          messages: [
            { id: 1, content: 'user prompt', sender: 'user', created_at: '2025-01-15T10:01:00Z' },
            { id: 2, content: 'ai draft', sender: 'ai', created_at: '2025-01-15T10:01:05Z' },
          ],
        }),
      ),
    );
    window.history.pushState({}, '', '/specialist/query/1');

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/headache consultation/i)).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: /approve and send/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /request revision/i })).toBeInTheDocument();
  });

  it('admin dashboard renders stat values', async () => {
    seedAuth({ role: 'admin', username: 'Admin User', email: 'admin@example.com' });
    window.history.pushState({}, '', '/admin/dashboard');

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/total ai responses/i)).toBeInTheDocument();
    });
    expect(screen.getByText('24')).toBeInTheDocument();
  });

  it('admin navigates all sections', async () => {
    seedAuth({ role: 'admin', username: 'Admin User', email: 'admin@example.com' });
    window.history.pushState({}, '', '/admin/dashboard');

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /dashboard/i })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('link', { name: /users/i }));
    await waitFor(() => expect(window.location.pathname).toBe('/admin/users'));

    fireEvent.click(screen.getByRole('link', { name: /chats/i }));
    await waitFor(() => expect(window.location.pathname).toBe('/admin/chats'));

    fireEvent.click(screen.getByRole('link', { name: /logs/i }));
    await waitFor(() => expect(window.location.pathname).toBe('/admin/logs'));
  });

  it('notification dropdown renders and marks read', async () => {
    seedAuth({ role: 'gp', username: 'Dr GP', email: 'gp@example.com' });
    const markReadSpy = vi.fn();
    server.use(
      http.get('/notifications/', () => HttpResponse.json(mockNotifications)),
      http.patch('/notifications/:notificationId/read', ({ params }) => {
        markReadSpy(Number(params.notificationId));
        return HttpResponse.json({
          ...mockNotifications[0],
          id: Number(params.notificationId),
          is_read: true,
        });
      }),
    );
    window.history.pushState({}, '', '/gp/queries');

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/my consultations/i)).toBeInTheDocument();
    });

    const bellButton = document.querySelector('button.relative.p-2') as HTMLButtonElement;
    expect(bellButton).toBeTruthy();
    fireEvent.click(bellButton);

    await waitFor(() => {
      expect(screen.getByText(/notifications/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText(mockNotifications[0].title));
    await waitFor(() => {
      expect(markReadSpy).toHaveBeenCalled();
    });
  });

  it('register page renders and submits', async () => {
    window.history.pushState({}, '', '/register');
    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /create your account/i })).toBeInTheDocument();
    });

    fireEvent.change(screen.getByLabelText(/first name/i), { target: { value: 'Test' } });
    fireEvent.change(screen.getByLabelText(/last name/i), { target: { value: 'User' } });
    fireEvent.change(screen.getByLabelText(/email address/i), {
      target: { value: 'new.gp@example.com' },
    });
    fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: 'Password123!' } });
    fireEvent.change(screen.getByLabelText(/^confirm password$/i), {
      target: { value: 'Password123!' },
    });

    fireEvent.click(screen.getByRole('button', { name: /create account/i }));

    await waitFor(() => {
      expect(window.location.pathname).toBe('/gp/queries');
    });
  });

  it('profile page shows user info', async () => {
    seedAuth({ role: 'gp', username: 'Dr GP', email: 'gp@example.com' });
    window.history.pushState({}, '', '/profile');

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /my profile/i })).toBeInTheDocument();
    });
    expect(screen.getByText('gp@example.com')).toBeInTheDocument();
  });

  it('api error shows fallback ui', async () => {
    seedAuth({ role: 'gp', username: 'Dr GP', email: 'gp@example.com' });
    server.use(
      http.get('/chats/:chatId', () =>
        HttpResponse.json({ detail: 'Server error' }, { status: 500 }),
      ),
    );
    window.history.pushState({}, '', '/gp/query/1');

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/consultation not found/i)).toBeInTheDocument();
    });
  });

  it('redirects a protected route to login when refresh and profile recovery fail', async () => {
    seedAuth({ role: 'gp', username: 'Dr GP', email: 'gp@example.com' });
    server.use(
      http.post('/auth/refresh', () =>
        HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 }),
      ),
      http.get('/auth/me', () => HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 })),
    );
    window.history.pushState({}, '', '/profile');

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /login to your account/i })).toBeInTheDocument();
    });
  });
});
