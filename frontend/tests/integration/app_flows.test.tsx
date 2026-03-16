import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';

import App from '@/App';
import { server } from '@test/mocks/server';
import { seedAuth } from '@test/utils';
import { mockChatWithMessages } from '@test/mocks/handlers';

describe('app integration flows', () => {
  it('boots an authenticated admin into the dashboard through the real app', async () => {
    seedAuth({ role: 'admin', username: 'Admin User', email: 'admin@example.com' });
    window.history.pushState({}, '', '/admin/dashboard');

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/total ai responses/i)).toBeInTheDocument();
    });
  });

  it('redirects a protected route to login when refresh and profile recovery fail', async () => {
    seedAuth({ role: 'gp', username: 'Dr GP', email: 'gp@example.com' });
    server.use(
      http.post('/auth/refresh', () =>
        HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 }),
      ),
      http.get('/auth/me', () =>
        HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 }),
      ),
    );
    window.history.pushState({}, '', '/profile');

    render(<App />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /login to your account/i })).toBeInTheDocument();
    });
  });

  it('renders citation dates through the full GP route', async () => {
    seedAuth({ role: 'gp', username: 'Dr GP', email: 'gp@example.com' });
    server.use(
      http.get('/chats/:chatId', ({ params }) =>
        HttpResponse.json({
          ...mockChatWithMessages,
          id: Number(params.chatId),
          messages: [
            mockChatWithMessages.messages[0],
            {
              id: 2,
              content: 'Grounded answer',
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
    expect(screen.getByText(/published 2024-01-01/i)).toBeInTheDocument();
    expect(screen.getByText(/nice ms guideline/i)).toBeInTheDocument();
  });
});
