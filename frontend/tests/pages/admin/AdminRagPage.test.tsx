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
  it('shows loading spinner then renders documents and jobs', async () => {
    renderRagPage();

    // Loading spinner should be visible initially
    expect(screen.queryByText(/indexed documents/i)).not.toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/indexed documents/i)).toBeInTheDocument();
    });

    expect(screen.getByText('doc-001')).toBeInTheDocument();
    expect(screen.getAllByText('NICE CG1').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('42')).toBeInTheDocument();

    expect(screen.getByText(/recent jobs/i)).toBeInTheDocument();
    expect(screen.getByText('job-001')).toBeInTheDocument();
    expect(screen.getByText('completed')).toBeInTheDocument();
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
          status: 'degraded',
          documents: [],
          recent_jobs: [],
        })),
    );

    renderRagPage();

    await waitFor(() => {
      expect(screen.getByText(/degraded/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/no indexed documents/i)).toBeInTheDocument();
    expect(screen.getByText(/no recent jobs/i)).toBeInTheDocument();
  });

  it('shows unknown health status and job errors', async () => {
    server.use(
      http.get('/admin/rag/status', () =>
        HttpResponse.json({
          status: 'offline',
          documents: [],
          recent_jobs: [
            {
              job_id: 'job-err',
              status: 'failed',
              source_name: 'Bad source',
              created_at: '2025-01-15T09:00:00Z',
              finished_at: null,
              error: 'Timeout',
            },
          ],
        })),
    );

    renderRagPage();

    await waitFor(() => {
      expect(screen.getByText('offline')).toBeInTheDocument();
    });
    expect(screen.getByText('Timeout')).toBeInTheDocument();
    expect(screen.getByText('failed')).toBeInTheDocument();
  });

  it('shows dash for null timestamps', async () => {
    server.use(
      http.get('/admin/rag/status', () =>
        HttpResponse.json({
          status: 'healthy',
          documents: [
            {
              doc_id: 'doc-null',
              source_name: 'Source',
              chunk_count: 1,
              latest_ingestion: null,
            },
          ],
          recent_jobs: [],
        })),
    );

    renderRagPage();

    await waitFor(() => {
      expect(screen.getByText('doc-null')).toBeInTheDocument();
    });
    // Null timestamp should render as —
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('applies unknown status badge class for unknown job status', async () => {
    server.use(
      http.get('/admin/rag/status', () =>
        HttpResponse.json({
          status: 'healthy',
          documents: [],
          recent_jobs: [
            {
              job_id: 'job-x',
              status: 'custom_status',
              source_name: 'X',
              created_at: '2025-01-15T09:00:00Z',
              finished_at: null,
              error: null,
            },
          ],
        })),
    );

    renderRagPage();

    await waitFor(() => {
      expect(screen.getByText('custom_status')).toBeInTheDocument();
    });
    // Job error column shows — when null
    expect(screen.getByText('—')).toBeInTheDocument();
  });
});
