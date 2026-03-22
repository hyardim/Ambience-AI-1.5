import { describe, it, expect } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { server } from '../../test/mocks/server';
import { renderWithProviders, seedAuth } from '../../test/utils';
import { AdminLogsPage } from './AdminLogsPage';

const API = 'http://localhost:8000';

describe('AdminLogsPage', () => {
  it('renders returned logs', async () => {
    seedAuth({ role: 'admin', username: 'Admin User' });
    server.use(
      http.get(`${API}/admin/logs`, () => {
        return HttpResponse.json([
          {
            id: 10,
            user_id: 1,
            user_identifier: 'gp@example.com',
            action: 'LOGIN',
            category: 'AUTH',
            details: 'User logged in',
            timestamp: '2025-01-15T10:00:00Z',
          },
        ]);
      }),
    );

    renderWithProviders(<AdminLogsPage />, { routes: ['/admin/logs'] });

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Audit Logs' })).toBeInTheDocument();
    });

    expect(screen.getByText('LOGIN')).toBeInTheDocument();
    expect(screen.getByText('User logged in')).toBeInTheDocument();
  });

  it('applies filters through the form', async () => {
    seedAuth({ role: 'admin', username: 'Admin User' });
    server.use(
      http.get(`${API}/admin/logs`, ({ request }) => {
        const url = new URL(request.url);
        if (url.searchParams.get('search') === 'abc') {
          return HttpResponse.json([]);
        }
        return HttpResponse.json([
          {
            id: 11,
            user_id: 2,
            user_identifier: 'specialist@example.com',
            action: 'REVIEW_APPROVE',
            category: 'SPECIALIST',
            details: 'Approved response',
            timestamp: '2025-01-15T11:00:00Z',
          },
        ]);
      }),
    );

    renderWithProviders(<AdminLogsPage />, { routes: ['/admin/logs'] });
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('REVIEW_APPROVE')).toBeInTheDocument();
    });

    await user.type(screen.getByPlaceholderText(/Search action or details/i), 'abc');
    await user.click(screen.getByRole('button', { name: /Apply/i }));

    await waitFor(() => {
      expect(screen.getByText(/No audit logs found/i)).toBeInTheDocument();
    });
  });
});
