import { describe, it, expect } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Routes, Route } from 'react-router-dom';
import { server } from '@test/mocks/server';
import { renderWithProviders, seedAuth } from '@test/utils';
import { SpecialistQueriesPage } from '@/pages/specialist/SpecialistQueriesPage';

function QueryDetailStub() {
  return <div>Specialist Query Detail</div>;
}

function renderSpecialistQueries() {
  seedAuth({ role: 'specialist', username: 'Dr Specialist' });
  return renderWithProviders(
    <Routes>
      <Route path="/specialist/queries" element={<SpecialistQueriesPage />} />
      <Route path="/specialist/query/:queryId" element={<QueryDetailStub />} />
    </Routes>,
    { routes: ['/specialist/queries'] },
  );
}

describe('SpecialistQueriesPage', () => {
  it('renders both tabs and loads data', async () => {
    renderSpecialistQueries();

    await waitFor(() => {
      expect(screen.getByText('Queries for Review')).toBeInTheDocument();
    });

    // Wait for data to load
    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    // Tabs should show counts
    expect(screen.getByText(/Queue \(1\)/i)).toBeInTheDocument();
    expect(screen.getByText(/My Assigned \(1\)/i)).toBeInTheDocument();
  });

  it('switches between Queue and Assigned tabs', async () => {
    renderSpecialistQueries();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    // Click on "My Assigned" tab
    await user.click(screen.getByText(/my assigned/i));

    await waitFor(() => {
      expect(screen.getByText('Joint pain assessment')).toBeInTheDocument();
    });
  });

  it('filters by search term', async () => {
    renderSpecialistQueries();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    await user.type(screen.getByPlaceholderText(/search by title or specialty/i), 'nonexistent');

    expect(screen.getByText('No queries found')).toBeInTheDocument();
  });

  it('shows error on API failure', async () => {
    server.use(
      http.get('/specialist/queue', () => {
        return HttpResponse.json({ detail: 'Error' }, { status: 500 });
      }),
    );

    renderSpecialistQueries();

    await waitFor(() => {
      expect(screen.getByText(/failed to load chats/i)).toBeInTheDocument();
    });
  });

  it('shows pending count badge', async () => {
    renderSpecialistQueries();

    await waitFor(() => {
      expect(screen.getByText(/pending/i)).toBeInTheDocument();
    });
  });

  it('has refresh button that reloads data', async () => {
    renderSpecialistQueries();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Refresh'));

    // Data should still be present after refresh
    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });
  });

  it('shows empty state for assigned tab with no chats', async () => {
    server.use(
      http.get('/specialist/assigned', () => {
        return HttpResponse.json([]);
      }),
    );

    renderSpecialistQueries();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/my assigned/i)).toBeInTheDocument();
    });

    await user.click(screen.getByText(/my assigned/i));

    await waitFor(() => {
      expect(screen.getByText('No queries found')).toBeInTheDocument();
    });
  });

  it('filters by status and severity and supports retry', async () => {
    server.use(
      http.get('/specialist/queue', () => HttpResponse.json({ detail: 'No backend' }, { status: 500 })),
    );

    renderSpecialistQueries();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/failed to load chats/i)).toBeInTheDocument();
    });

    server.use(
      http.get('/specialist/queue', () =>
        HttpResponse.json([
          {
            id: 1,
            title: 'Urgent neuro',
            status: 'submitted',
            specialty: 'neurology',
            severity: 'urgent',
            specialist_id: null,
            assigned_at: null,
            reviewed_at: null,
            review_feedback: null,
            created_at: '2025-01-15T10:00:00Z',
            user_id: 1,
          },
        ])),
    );

    await user.click(screen.getByRole('button', { name: /retry/i }));
    await user.selectOptions(screen.getByDisplayValue(/all status/i), 'submitted');
    await user.selectOptions(screen.getByDisplayValue(/all severity/i), 'urgent');

    await waitFor(() => {
      expect(screen.getByText(/urgent neuro/i)).toBeInTheDocument();
    });
  });

  it('lets specialists reselect the queue tab and open a consultation card', async () => {
    renderSpecialistQueries();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    await user.click(screen.getByText(/queue/i));
    await user.click(screen.getByText('Headache consultation'));

    expect(screen.getByText('Specialist Query Detail')).toBeInTheDocument();
  });

  it('renders fallback title, specialty, and assigned date details', async () => {
    server.use(
      http.get('/specialist/queue', () =>
        HttpResponse.json([
          {
            id: 4,
            title: '',
            status: 'submitted',
            specialty: null,
            severity: null,
            specialist_id: null,
            assigned_at: '2025-01-16T10:00:00Z',
            reviewed_at: null,
            review_feedback: null,
            created_at: '2025-01-15T10:00:00Z',
            user_id: 1,
          },
        ])),
      http.get('/specialist/assigned', () => HttpResponse.json([])),
    );

    renderSpecialistQueries();

    await waitFor(() => {
      expect(screen.getByText(/untitled consultation/i)).toBeInTheDocument();
    });
    expect(screen.queryByText('—')).not.toBeInTheDocument();
    expect(screen.getByText(/assigned 16 jan 2025/i)).toBeInTheDocument();
  });
});
