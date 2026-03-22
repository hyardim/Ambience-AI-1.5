import { describe, it, expect } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { server } from '../../test/mocks/server';
import { renderWithProviders, seedAuth } from '../../test/utils';
import AdminDashboardPage from './AdminDashboardPage';

const API = 'http://localhost:8000';

const statsPayload = {
  total_ai_responses: 12,
  rag_grounded_responses: 9,
  active_consultations: 5,
  active_users_by_role: { gp: 3, specialist: 2, admin: 1 },
  chats_by_status: { open: 2, submitted: 3 },
  chats_by_specialty: { neurology: 2, rheumatology: 3 },
  daily_ai_queries: [{ date: '2025-01-01', count: 4 }],
};

describe('AdminDashboardPage', () => {
  it('renders stats after loading', async () => {
    seedAuth({ role: 'admin', username: 'Admin User' });
    server.use(http.get(`${API}/admin/stats`, () => HttpResponse.json(statsPayload)));

    renderWithProviders(<AdminDashboardPage />, { routes: ['/admin/dashboard'] });

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Dashboard' })).toBeInTheDocument();
    });

    expect(screen.getByText('Total AI Responses')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
  });

  it('shows an error when stats endpoint fails and can refresh', async () => {
    seedAuth({ role: 'admin', username: 'Admin User' });
    let shouldFail = true;
    server.use(
      http.get(`${API}/admin/stats`, () => {
        if (shouldFail) return HttpResponse.json({ detail: 'Stats unavailable' }, { status: 500 });
        return HttpResponse.json(statsPayload);
      }),
    );

    renderWithProviders(<AdminDashboardPage />, { routes: ['/admin/dashboard'] });

    await waitFor(() => {
      expect(screen.getByText(/Stats unavailable/i)).toBeInTheDocument();
    });

    shouldFail = false;
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /Refresh/i }));

    await waitFor(() => {
      expect(screen.getByText('Total AI Responses')).toBeInTheDocument();
    });
  });
});
