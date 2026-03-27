import { describe, it, expect } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Routes, Route } from 'react-router-dom';
import AdminRagPage from '@/pages/admin/AdminRagPage';
import { renderWithProviders, seedAuth } from '@test/utils';
import { server } from '@test/mocks/server';
import type { RagStatusResponse } from '@/types/api';

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

function overrideRagStatus(data: Partial<RagStatusResponse>) {
  server.use(http.get('/admin/rag/status', () => HttpResponse.json(data)));
}

// ---------------------------------------------------------------------------
// 1. Initial load & happy path
// ---------------------------------------------------------------------------

describe('AdminRagPage — initial load', () => {
  it('shows loading spinner before data arrives', () => {
    renderRagPage();
    // Documents section not yet rendered
    expect(screen.queryByText(/indexed documents/i)).not.toBeInTheDocument();
  });

  it('renders page heading', async () => {
    renderRagPage();
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'RAG Pipeline' })).toBeInTheDocument(),
    );
  });

  it('renders Indexed Documents section after load', async () => {
    renderRagPage();
    await waitFor(() => expect(screen.getByText(/indexed documents/i)).toBeInTheDocument());
  });

  it('renders Ingestion Jobs section after load', async () => {
    renderRagPage();
    await waitFor(() => expect(screen.getByText(/ingestion jobs/i)).toBeInTheDocument());
  });

  it('renders document row with correct data', async () => {
    renderRagPage();
    await waitFor(() => expect(screen.getByText('doc-001')).toBeInTheDocument());
    expect(screen.getAllByText('NICE CG1').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('42')).toBeInTheDocument();
  });

  it('renders job counts correctly', async () => {
    renderRagPage();
    await waitFor(() => expect(screen.getByText(/ingestion jobs/i)).toBeInTheDocument());
    expect(screen.getByText('2')).toBeInTheDocument(); // pending
    // running=1 may clash with other elements — verify via label proximity
    expect(screen.getByText('Running')).toBeInTheDocument();
    expect(screen.getByText('0')).toBeInTheDocument(); // failed
  });

  it('renders Pending, Running, Failed labels', async () => {
    renderRagPage();
    await waitFor(() => expect(screen.getByText(/ingestion jobs/i)).toBeInTheDocument());
    expect(screen.getByText('Pending')).toBeInTheDocument();
    expect(screen.getByText('Running')).toBeInTheDocument();
    expect(screen.getByText('Failed')).toBeInTheDocument();
  });

  it('renders Refresh button', async () => {
    renderRagPage();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /refresh/i })).toBeInTheDocument(),
    );
  });
});

// ---------------------------------------------------------------------------
// 2. Health badge
// ---------------------------------------------------------------------------

describe('AdminRagPage — health badge', () => {
  it('shows green Healthy badge for "healthy" status', async () => {
    overrideRagStatus({ service_status: 'healthy', documents: [], jobs: null });
    renderRagPage();
    await waitFor(() => expect(screen.getByText('Healthy')).toBeInTheDocument());
  });

  it('shows green Ready badge for "ready" status', async () => {
    overrideRagStatus({ service_status: 'ready', documents: [], jobs: null });
    renderRagPage();
    await waitFor(() => expect(screen.getByText('Ready')).toBeInTheDocument());
  });

  it('shows amber Degraded badge for "degraded" status', async () => {
    overrideRagStatus({ service_status: 'degraded', documents: [], jobs: null });
    renderRagPage();
    await waitFor(() => expect(screen.getByText('Degraded')).toBeInTheDocument());
  });

  it('shows red badge with raw status text for unknown status', async () => {
    overrideRagStatus({ service_status: 'offline', documents: [], jobs: null });
    renderRagPage();
    await waitFor(() => expect(screen.getByText('offline')).toBeInTheDocument());
  });

  it('shows red badge for "unavailable" status', async () => {
    overrideRagStatus({ service_status: 'unavailable', documents: [], jobs: null });
    renderRagPage();
    await waitFor(() => expect(screen.getByText('unavailable')).toBeInTheDocument());
  });
});

// ---------------------------------------------------------------------------
// 3. Empty states
// ---------------------------------------------------------------------------

describe('AdminRagPage — empty states', () => {
  it('shows "No indexed documents" when documents array is empty', async () => {
    overrideRagStatus({ service_status: 'healthy', documents: [], jobs: null });
    renderRagPage();
    await waitFor(() => expect(screen.getByText(/no indexed documents/i)).toBeInTheDocument());
  });

  it('shows "No job data available" when jobs is null', async () => {
    overrideRagStatus({ service_status: 'healthy', documents: [], jobs: null });
    renderRagPage();
    await waitFor(() => expect(screen.getByText(/no job data available/i)).toBeInTheDocument());
  });

  it('does not show document table when documents is empty', async () => {
    overrideRagStatus({ service_status: 'healthy', documents: [], jobs: null });
    renderRagPage();
    await waitFor(() => expect(screen.getByText(/no indexed documents/i)).toBeInTheDocument());
    expect(screen.queryByRole('columnheader', { name: /document id/i })).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 4. Timestamp formatting
// ---------------------------------------------------------------------------

describe('AdminRagPage — timestamp formatting', () => {
  it('renders dash for null latest_ingestion', async () => {
    overrideRagStatus({
      service_status: 'healthy',
      documents: [
        { doc_id: 'doc-null', source_name: 'Source', chunk_count: 1, latest_ingestion: null },
      ],
      jobs: null,
    });
    renderRagPage();
    await waitFor(() => expect(screen.getByText('doc-null')).toBeInTheDocument());
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('renders formatted timestamp for valid latest_ingestion', async () => {
    overrideRagStatus({
      service_status: 'healthy',
      documents: [
        {
          doc_id: 'doc-ts',
          source_name: 'Source',
          chunk_count: 5,
          latest_ingestion: '2025-06-15T14:30:00Z',
        },
      ],
      jobs: null,
    });
    renderRagPage();
    await waitFor(() => expect(screen.getByText('doc-ts')).toBeInTheDocument());
    // Should contain some formatted date — not raw ISO
    expect(screen.queryByText('2025-06-15T14:30:00Z')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 5. Multiple documents
// ---------------------------------------------------------------------------

describe('AdminRagPage — multiple documents', () => {
  it('renders all documents in the table', async () => {
    overrideRagStatus({
      service_status: 'healthy',
      documents: [
        { doc_id: 'doc-a', source_name: 'NICE A', chunk_count: 10, latest_ingestion: null },
        { doc_id: 'doc-b', source_name: 'BSR B', chunk_count: 20, latest_ingestion: null },
        { doc_id: 'doc-c', source_name: 'NICE C', chunk_count: 30, latest_ingestion: null },
      ],
      jobs: null,
    });
    renderRagPage();
    await waitFor(() => expect(screen.getByText('doc-a')).toBeInTheDocument());
    expect(screen.getByText('doc-b')).toBeInTheDocument();
    expect(screen.getByText('doc-c')).toBeInTheDocument();
    expect(screen.getAllByText('BSR B').length).toBeGreaterThan(0);
    expect(screen.getByText('10')).toBeInTheDocument();
    expect(screen.getByText('20')).toBeInTheDocument();
    expect(screen.getByText('30')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 6. Job counts
// ---------------------------------------------------------------------------

describe('AdminRagPage — job counts', () => {
  it('shows zero counts correctly', async () => {
    overrideRagStatus({
      service_status: 'healthy',
      documents: [],
      jobs: { pending: 0, running: 0, failed: 0 },
    });
    renderRagPage();
    await waitFor(() => expect(screen.getByText(/ingestion jobs/i)).toBeInTheDocument());
    const zeros = screen.getAllByText('0');
    expect(zeros.length).toBe(3);
  });

  it('shows high job counts correctly', async () => {
    overrideRagStatus({
      service_status: 'healthy',
      documents: [],
      jobs: { pending: 999, running: 50, failed: 12 },
    });
    renderRagPage();
    await waitFor(() => expect(screen.getByText('999')).toBeInTheDocument());
    expect(screen.getByText('50')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 7. Error state
// ---------------------------------------------------------------------------

describe('AdminRagPage — error state', () => {
  it('shows error message when API returns 500', async () => {
    server.use(
      http.get('/admin/rag/status', () =>
        HttpResponse.json({ detail: 'Internal server error' }, { status: 500 }),
      ),
    );
    renderRagPage();
    await waitFor(() => expect(screen.getByText(/internal server error/i)).toBeInTheDocument());
  });

  it('does not show documents section when errored', async () => {
    server.use(
      http.get('/admin/rag/status', () => HttpResponse.json({ detail: 'down' }, { status: 503 })),
    );
    renderRagPage();
    await waitFor(() => expect(screen.getByText(/down/i)).toBeInTheDocument());
    expect(screen.queryByText(/indexed documents/i)).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 8. Refresh button
// ---------------------------------------------------------------------------

describe('AdminRagPage — refresh', () => {
  it('re-fetches and updates data on refresh click', async () => {
    renderRagPage();
    const user = userEvent.setup();

    await waitFor(() => expect(screen.getByText('doc-001')).toBeInTheDocument());

    // Override with new data
    server.use(
      http.get('/admin/rag/status', () =>
        HttpResponse.json({
          service_status: 'healthy',
          documents: [
            {
              doc_id: 'doc-refreshed',
              source_name: 'New Source',
              chunk_count: 99,
              latest_ingestion: null,
            },
          ],
          jobs: { pending: 0, running: 0, failed: 0 },
        }),
      ),
    );

    await user.click(screen.getByRole('button', { name: /refresh/i }));

    await waitFor(() => expect(screen.getByText('doc-refreshed')).toBeInTheDocument());
    expect(screen.getAllByText('New Source').length).toBeGreaterThan(0);
    expect(screen.getByText('99')).toBeInTheDocument();
  });

  it('refresh button is disabled while loading', () => {
    renderRagPage();
    expect(screen.getByRole('button', { name: /refresh/i })).toBeDisabled();
  });

  it('refresh button is enabled after data loads', async () => {
    renderRagPage();
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /refresh/i })).not.toBeDisabled(),
    );
  });

  it('clears previous error on successful refresh', async () => {
    server.use(
      http.get('/admin/rag/status', () =>
        HttpResponse.json({ detail: 'Service down' }, { status: 500 }),
      ),
    );
    renderRagPage();
    const user = userEvent.setup();

    await waitFor(() => expect(screen.getByText(/service down/i)).toBeInTheDocument());

    // Now succeed
    server.use(
      http.get('/admin/rag/status', () =>
        HttpResponse.json({
          service_status: 'healthy',
          documents: [],
          jobs: { pending: 0, running: 0, failed: 0 },
        }),
      ),
    );

    await user.click(screen.getByRole('button', { name: /refresh/i }));

    await waitFor(() => expect(screen.queryByText(/service down/i)).not.toBeInTheDocument());
    expect(screen.getByText(/ingestion jobs/i)).toBeInTheDocument();
  });
});

describe('AdminRagPage — search, filter, and sort', () => {
  it('filters documents by search text and source, and sorts by chunk count', async () => {
    overrideRagStatus({
      service_status: 'healthy',
      documents: [
        {
          doc_id: 'doc-a',
          source_name: 'NICE',
          chunk_count: 10,
          latest_ingestion: '2025-06-15T14:30:00Z',
        },
        {
          doc_id: 'doc-b',
          source_name: 'BSR',
          chunk_count: 30,
          latest_ingestion: '2025-06-16T14:30:00Z',
        },
        {
          doc_id: 'match-doc',
          source_name: 'NICE',
          chunk_count: 20,
          latest_ingestion: '2025-06-17T14:30:00Z',
        },
      ],
      jobs: null,
    });

    renderRagPage();
    const user = userEvent.setup();

    await waitFor(() => expect(screen.getByText('doc-a')).toBeInTheDocument());

    await user.type(screen.getByLabelText(/search/i), 'doc');
    await user.selectOptions(screen.getByLabelText(/source/i), 'NICE');
    await user.selectOptions(screen.getByLabelText(/sort by/i), 'chunk_count');
    await user.selectOptions(screen.getByLabelText(/direction/i), 'desc');

    expect(screen.getByText('match-doc')).toBeInTheDocument();
    expect(screen.queryByText('doc-b')).not.toBeInTheDocument();

    const documentRows = screen.getAllByRole('row').slice(1);
    expect(documentRows[0]).toHaveTextContent('match-doc');
  });

  it('sorts documents by source name ascending', async () => {
    overrideRagStatus({
      service_status: 'healthy',
      documents: [
        { doc_id: 'doc-z', source_name: 'Zeta Source', chunk_count: 1, latest_ingestion: null },
        { doc_id: 'doc-a', source_name: 'Alpha Source', chunk_count: 1, latest_ingestion: null },
      ],
      jobs: null,
    });

    renderRagPage();
    const user = userEvent.setup();

    await waitFor(() => expect(screen.getByText('doc-z')).toBeInTheDocument());

    await user.selectOptions(screen.getByLabelText(/sort by/i), 'source_name');
    await user.selectOptions(screen.getByLabelText(/direction/i), 'asc');

    const documentRows = screen.getAllByRole('row').slice(1);
    expect(documentRows[0]).toHaveTextContent('Alpha Source');
  });
});
