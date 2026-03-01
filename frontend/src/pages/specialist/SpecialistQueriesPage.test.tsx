import { describe, it, expect } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Routes, Route } from 'react-router-dom';
import { server } from '../../test/mocks/server';
import { renderWithProviders, seedAuth } from '../../test/utils';
import { SpecialistQueriesPage } from './SpecialistQueriesPage';

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
});
