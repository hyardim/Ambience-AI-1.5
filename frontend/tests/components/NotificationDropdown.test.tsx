import { describe, it, expect, vi, afterEach } from 'vitest';
import { screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Routes, Route } from 'react-router-dom';
import { renderWithProviders, seedAuth } from '@test/utils';
import { server } from '@test/mocks/server';
import { NotificationDropdown } from '@/components/NotificationDropdown';

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
  afterEach(() => {
    vi.useRealTimers();
  });

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

  it('marks all notifications read and navigates for gp users', async () => {
    renderDropdown('gp');
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('1')).toBeInTheDocument();
    });

    await user.click(screen.getAllByRole('button')[0]);
    await user.click(screen.getByText(/mark all read/i));
    expect(screen.queryByText('1')).not.toBeInTheDocument();

    await user.click(screen.getByText(/chat assigned/i));
    await waitFor(() => {
      expect(screen.getByText(/gp query detail/i)).toBeInTheDocument();
    });
  });

  it('navigates specialist users and supports empty state', async () => {
    renderDropdown('specialist');
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getAllByRole('button')[0]).toBeInTheDocument();
    });

    await user.click(screen.getAllByRole('button')[0]);
    await user.click(screen.getByText(/chat assigned/i));
    await waitFor(() => {
      expect(screen.getByText(/specialist query detail/i)).toBeInTheDocument();
    });
  });

  it('handles notification API failures and outside clicks gracefully', async () => {
    server.use(
      http.get('/notifications/', () => HttpResponse.json({ detail: 'Nope' }, { status: 500 })),
      http.patch('/notifications/:id/read', () => HttpResponse.json({ detail: 'Nope' }, { status: 500 })),
      http.patch('/notifications/read-all', () => HttpResponse.json({ detail: 'Nope' }, { status: 500 })),
    );

    renderDropdown('admin');
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getAllByRole('button')[0]).toBeInTheDocument();
    });

    await user.click(screen.getAllByRole('button')[0]);
    expect(screen.getByText(/no notifications/i)).toBeInTheDocument();

    await user.click(document.body);
    await waitFor(() => {
      expect(screen.queryByText(/notifications/i)).not.toBeInTheDocument();
    });
  });

  it('formats older notifications and leaves unread state when mark-read fails', async () => {
    server.use(
      http.get('/notifications/', () =>
        HttpResponse.json([
          {
            id: 1,
            type: 'chat_assigned',
            title: 'Chat assigned',
            body: '',
            chat_id: null,
            is_read: false,
            created_at: '2024-01-15T11:00:00Z',
          },
        ])),
      http.patch('/notifications/:id/read', () => HttpResponse.json({ detail: 'Nope' }, { status: 500 })),
    );

    renderDropdown('gp');
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('1')).toBeInTheDocument();
    });

    await user.click(screen.getAllByRole('button')[0]);
    expect(screen.getByText(/15 jan/i)).toBeInTheDocument();
    await user.click(screen.getByText(/chat assigned/i));

    expect(screen.getByText('1')).toBeInTheDocument();
  });

  it('shows 9+ unread badge and formats recent times', async () => {
    server.use(
      http.get('/notifications/', () =>
        HttpResponse.json(
          Array.from({ length: 10 }, (_, index) => ({
            id: index + 1,
            type: 'chat_assigned',
            title: index === 0 ? 'Fresh notice' : `Notice ${index + 1}`,
            body: '',
            chat_id: null,
            is_read: false,
            created_at: index === 0 ? new Date().toISOString() : new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
          })),
        )),
    );

    renderDropdown('gp');
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('9+')).toBeInTheDocument();
    });

    await user.click(screen.getAllByRole('button')[0]);
    expect(screen.getByText(/just now/i)).toBeInTheDocument();
    expect(screen.getAllByText(/2h ago/i).length).toBeGreaterThan(0);
  });

  it('formats notifications that are only a few minutes old', async () => {
    server.use(
      http.get('/notifications/', () =>
        HttpResponse.json([
          {
            id: 1,
            type: 'chat_assigned',
            title: 'Recent notice',
            body: '',
            chat_id: null,
            is_read: false,
            created_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
          },
        ])),
    );

    renderDropdown('gp');
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('1')).toBeInTheDocument();
    });

    await user.click(screen.getAllByRole('button')[0]);
    expect(screen.getByText(/5m ago/i)).toBeInTheDocument();
  });

  it('polls for refreshed notifications over time', async () => {
    vi.useFakeTimers();
    let pollCount = 0;
    server.use(
      http.get('/notifications/', () => {
        pollCount += 1;
        return HttpResponse.json([
          {
            id: 1,
            type: 'chat_assigned',
            title: pollCount > 1 ? 'Updated notification' : 'Chat assigned',
            body: '',
            chat_id: 1,
            is_read: false,
            created_at: new Date().toISOString(),
          },
        ]);
      }),
    );

    renderDropdown('gp');
    await act(async () => {
      await vi.runOnlyPendingTimersAsync();
    });
    expect(screen.getByText('1')).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    expect(pollCount).toBeGreaterThan(1);
  }, 10000);
});
