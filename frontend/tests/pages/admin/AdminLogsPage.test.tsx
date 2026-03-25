import { describe, it, expect } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Routes, Route } from 'react-router-dom';
import { AdminLogsPage } from '@/pages/admin/AdminLogsPage';
import { renderWithProviders, seedAuth } from '@test/utils';
import { server } from '@test/mocks/server';

function renderPage() {
  seedAuth({ role: 'admin', username: 'Admin' });
  return renderWithProviders(
    <Routes>
      <Route path="/admin/logs" element={<AdminLogsPage />} />
      <Route path="/login" element={<div>Login</div>} />
    </Routes>,
    { routes: ['/admin/logs'] },
  );
}

describe('AdminLogsPage', () => {
  it('renders logs and applies filters', async () => {
    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /audit logs/i })).toBeInTheDocument();
    });

    expect(screen.getByText(/gp_1/i)).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText(/search action or details/i), 'login');
    await user.selectOptions(screen.getByDisplayValue('All categories'), 'AUTH');
    await user.click(screen.getByRole('button', { name: /apply/i }));

    expect(screen.getByText(/LOGIN/)).toBeInTheDocument();
  });

  it('shows empty and error states', async () => {
    server.use(http.get('/admin/logs', () => HttpResponse.json([])));
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/No audit logs found/i)).toBeInTheDocument();
    });

    server.use(http.get('/admin/logs', () => HttpResponse.json({ detail: 'Nope' }, { status: 500 })));
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /refresh/i }));

    await waitFor(() => {
      expect(screen.getByText(/nope|failed to load audit logs/i)).toBeInTheDocument();
    });
  });

  it('supports extended filters and unknown style fallbacks', async () => {
    server.use(
      http.get('/admin/logs', ({ request }) => {
        const url = new URL(request.url);
        expect(url.searchParams.get('action')).toBe('CUSTOM_ACTION');
        expect(url.searchParams.get('user_id')).toBe('42');
        expect(url.searchParams.get('date_from')).toBe('2025-01-01T09:00');
        expect(url.searchParams.get('date_to')).toBe('2025-01-31T17:00');
        expect(url.searchParams.get('limit')).toBe('500');
        return HttpResponse.json([
          {
            id: 2,
            user_id: 42,
            user_identifier: '',
            action: 'CUSTOM_ACTION',
            category: 'UNKNOWN',
            details: '',
            timestamp: '2025-01-15T10:00:00Z',
          },
        ]);
      }),
    );

    renderPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /audit logs/i })).toBeInTheDocument();
    });

    await user.type(screen.getByPlaceholderText(/exact action/i), 'CUSTOM_ACTION');
    await user.type(screen.getByPlaceholderText(/user id/i), '42');
    const [fromInput, toInput] = screen.getAllByTitle(/date/i) as HTMLInputElement[];
    fireEvent.change(fromInput, { target: { value: '2025-01-01T09:00' } });
    fireEvent.change(toInput, { target: { value: '2025-01-31T17:00' } });
    await user.selectOptions(screen.getByDisplayValue('200 rows'), '500');
    await user.click(screen.getByRole('button', { name: /apply/i }));

    await waitFor(() => {
      expect(screen.getByText('CUSTOM_ACTION')).toBeInTheDocument();
    });

    expect(screen.getByText('UNKNOWN')).toBeInTheDocument();
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('falls back to user-id labels when no user identifier is present', async () => {
    server.use(
      http.get('/admin/logs', () => HttpResponse.json([
        {
          id: 3,
          user_id: 42,
          user_identifier: null,
          action: 'LOGIN',
          category: 'AUTH',
          details: 'Signed in',
          timestamp: '2025-01-15T10:00:00Z',
        },
      ])),
    );

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('#42')).toBeInTheDocument();
    });
  });
});
