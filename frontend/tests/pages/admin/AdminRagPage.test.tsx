import { describe, it, expect } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Routes, Route } from 'react-router-dom';
import AdminRagPage from '@/pages/admin/AdminRagPage';
import { renderWithProviders, seedAuth } from '@test/utils';
import { server } from '@test/mocks/server';

function renderRagPage() {
  seedAuth({ role: 'admin', username: 'Admin' });
  return renderWithProviders(
    <Routes>
      <Route path="/admin/rag" element={<AdminRagPage />} />
      <Route path="/login" element={<div>Login</div>} />
    </Routes>,
    { routes: ['/admin/rag'] },
  );
}

describe('AdminRagPage', () => {
  it('shows loading spinner then renders documents and job summary', async () => {
    renderRagPage();

    // Loading spinner should be visible initially
    expect(screen.queryByText(/indexed documents/i)).not.toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/indexed documents/i)).toBeInTheDocument();
    });

    expect(screen.getByText('doc-001')).toBeInTheDocument();
    expect(screen.getAllByText('NICE CG1').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('42')).toBeInTheDocument();

    expect(screen.getByText(/job summary/i)).toBeInTheDocument();
    expect(screen.getAllByText('1').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('pending')).toBeInTheDocument();
    expect(screen.getByText(/healthy/i)).toBeInTheDocument();
  });

  it('shows error state when API fails', async () => {
    server.use(
      http.get('/admin/rag/status', () =>
        HttpResponse.json({ detail: 'Service down' }, { status: 500 })),
    );

    renderRagPage();

    await waitFor(() => {
      expect(screen.getByText(/service down/i)).toBeInTheDocument();
    });
  });

  it('refreshes data when clicking refresh button', async () => {
    renderRagPage();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/indexed documents/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /refresh/i }));

    await waitFor(() => {
      expect(screen.getByText('doc-001')).toBeInTheDocument();
    });
  });

  it('shows degraded health badge', async () => {
    server.use(
      http.get('/admin/rag/status', () =>
        HttpResponse.json({
          service_status: 'degraded',
          documents: [],
          jobs: null,
        })),
    );

    renderRagPage();

    await waitFor(() => {
      expect(screen.getByText(/degraded/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/no indexed documents/i)).toBeInTheDocument();
    expect(screen.getByText(/no job summary available/i)).toBeInTheDocument();
  });

  it('shows unknown health status and failed job count', async () => {
    server.use(
      http.get('/admin/rag/status', () =>
        HttpResponse.json({
          service_status: 'offline',
          documents: [],
          jobs: { pending: 0, running: 0, failed: 3 },
        })),
    );

    renderRagPage();

    await waitFor(() => {
      expect(screen.getByText('offline')).toBeInTheDocument();
    });
    expect(screen.getByText('failed')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  it('shows dash for null timestamps', async () => {
    server.use(
      http.get('/admin/rag/status', () =>
        HttpResponse.json({
          service_status: 'healthy',
          documents: [
            {
              doc_id: 'doc-null',
              source_name: 'Source',
              chunk_count: 1,
              latest_ingestion: null,
            },
          ],
          jobs: { pending: 0, running: 0, failed: 0 },
        })),
    );

    renderRagPage();

    await waitFor(() => {
      expect(screen.getByText('doc-null')).toBeInTheDocument();
    });
    // Null timestamp should render as —
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('shows job counters when provided', async () => {
    server.use(
      http.get('/admin/rag/status', () =>
        HttpResponse.json({
          service_status: 'healthy',
          documents: [],
          jobs: { pending: 2, running: 1, failed: 4 },
        })),
    );

    renderRagPage();

    await waitFor(() => {
      expect(screen.getByText('running')).toBeInTheDocument();
    });
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('4')).toBeInTheDocument();
  });
});
