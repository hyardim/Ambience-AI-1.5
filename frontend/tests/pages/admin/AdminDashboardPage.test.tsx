import { describe, it, expect, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Routes, Route } from 'react-router-dom';
import AdminDashboardPage from '@/pages/admin/AdminDashboardPage';
import { renderWithProviders, seedAuth } from '@test/utils';
import { server } from '@test/mocks/server';

vi.mock('recharts', () => {
  const Mock = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>;
  const XAxis = ({ tickFormatter }: { tickFormatter?: (value: string) => string }) => (
    <div>{tickFormatter ? tickFormatter('2025-01-15') : null}</div>
  );
  const Tooltip = ({ labelFormatter }: { labelFormatter?: (value: string) => string }) => (
    <div>{labelFormatter ? labelFormatter('2025-01-15') : null}</div>
  );
  return {
    ResponsiveContainer: Mock,
    AreaChart: Mock,
    Area: Mock,
    BarChart: Mock,
    Bar: Mock,
    PieChart: Mock,
    Pie: Mock,
    Cell: Mock,
    XAxis,
    YAxis: Mock,
    CartesianGrid: Mock,
    Tooltip,
    Legend: Mock,
  };
});

function renderDashboard() {
  seedAuth({ role: 'admin', username: 'Admin' });
  return renderWithProviders(
    <Routes>
      <Route path="/admin/dashboard" element={<AdminDashboardPage />} />
      <Route path="/login" element={<div>Login</div>} />
    </Routes>,
    { routes: ['/admin/dashboard'] },
  );
}

describe('AdminDashboardPage', () => {
  it('renders stats and rag logs', async () => {
    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText(/Total AI Responses/)).toBeInTheDocument();
    });

    expect(screen.getByText(/RAG-Grounded/)).toBeInTheDocument();
    expect(screen.getByText(/Recent RAG Logs/)).toBeInTheDocument();
  });

  it('shows empty states and refreshes', async () => {
    server.use(
      http.get('/admin/stats', () =>
        HttpResponse.json({
          total_ai_responses: 0,
          rag_grounded_responses: 0,
          active_consultations: 0,
          active_users_by_role: { gp: 0, specialist: 0, admin: 1 },
          chats_by_status: {},
          chats_by_specialty: {},
          daily_ai_queries: [],
        }),
      ),
      http.get('/admin/logs', () => HttpResponse.json([])),
    );

    renderDashboard();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/No data/)).toBeInTheDocument();
    });
    expect(screen.getByText(/No recent RAG activity/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /refresh/i }));
  });

  it('shows load errors', async () => {
    server.use(
      http.get('/admin/stats', () => HttpResponse.json({ detail: 'Boom' }, { status: 500 })),
    );

    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText(/boom|failed to load stats/i)).toBeInTheDocument();
    });
  });

  it('shows rag log failure without hiding successful stats', async () => {
    server.use(
      http.get('/admin/stats', () =>
        HttpResponse.json({
          total_ai_responses: 4,
          rag_grounded_responses: 2,
          active_consultations: 1,
          active_users_by_role: { gp: 1, specialist: 1, admin: 1 },
          chats_by_status: { open: 1 },
          chats_by_specialty: { neurology: 1 },
          daily_ai_queries: [],
        }),
      ),
      http.get('/admin/logs', () =>
        HttpResponse.json({ detail: 'RAG logs unavailable' }, { status: 500 }),
      ),
    );

    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText(/total ai responses/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/rag logs unavailable|failed to load rag logs/i)).toBeInTheDocument();
  });

  it('renders query and log fallbacks for partially empty datasets', async () => {
    server.use(
      http.get('/admin/stats', () =>
        HttpResponse.json({
          total_ai_responses: 5,
          rag_grounded_responses: 0,
          active_consultations: 2,
          active_users_by_role: { gp: 1, specialist: 1, admin: 1 },
          chats_by_status: { open: 2 },
          chats_by_specialty: { neurology: 2 },
          daily_ai_queries: [],
        }),
      ),
      http.get('/admin/logs', () => HttpResponse.json([])),
    );

    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText(/No query data in the last 30 days/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/No recent RAG activity/i)).toBeInTheDocument();
  });

  it('renders unknown status colours, missing specialist counts, and log detail fallbacks', async () => {
    server.use(
      http.get('/admin/stats', () =>
        HttpResponse.json({
          total_ai_responses: 5,
          rag_grounded_responses: 1,
          active_consultations: 2,
          active_users_by_role: { gp: 1, admin: 1 },
          chats_by_status: { custom: 2 },
          chats_by_specialty: { neurology: 2 },
          daily_ai_queries: [{ date: '2025-01-15', count: 2 }],
        }),
      ),
      http.get('/admin/logs', () =>
        HttpResponse.json([
          {
            id: 1,
            user_id: 1,
            user_identifier: 'admin_1',
            category: 'RAG',
            action: 'CUSTOM',
            details: '',
            timestamp: '2025-01-15T10:00:00Z',
          },
        ]),
      ),
    );

    renderDashboard();

    await waitFor(() => {
      expect(screen.getByText(/0 specialists/i)).toBeInTheDocument();
    });
    expect(screen.getAllByText(/date: 2025-01-15/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/^—$/)).toBeInTheDocument();
  });
});
