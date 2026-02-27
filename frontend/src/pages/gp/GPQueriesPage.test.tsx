import { describe, it, expect, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Routes, Route } from 'react-router-dom';
import { server } from '../../test/mocks/server';
import { renderWithProviders, seedAuth } from '../../test/utils';
import { GPQueriesPage } from './GPQueriesPage';

function NewQueryStub() {
  return <div>New Query Page</div>;
}
function QueryDetailStub() {
  return <div>Query Detail Page</div>;
}

function renderGPQueries() {
  seedAuth({ role: 'gp' });
  return renderWithProviders(
    <Routes>
      <Route path="/gp/queries" element={<GPQueriesPage />} />
      <Route path="/gp/queries/new" element={<NewQueryStub />} />
      <Route path="/gp/query/:queryId" element={<QueryDetailStub />} />
      <Route path="/login" element={<div>Login</div>} />
    </Routes>,
    { routes: ['/gp/queries'] },
  );
}

describe('GPQueriesPage', () => {
  it('shows loading spinner then renders consultations', async () => {
    renderGPQueries();

    // Loading state (spinner has animate-spin class)
    await waitFor(() => {
      expect(screen.getByText('My Consultations')).toBeInTheDocument();
    });

    // Wait for chats to load
    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    expect(screen.getByText('Joint pain assessment')).toBeInTheDocument();
  });

  it('filters chats by search term', async () => {
    renderGPQueries();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    await user.type(screen.getByPlaceholderText(/search by title/i), 'Joint');

    expect(screen.queryByText('Headache consultation')).not.toBeInTheDocument();
    expect(screen.getByText('Joint pain assessment')).toBeInTheDocument();
  });

  it('shows empty state when no chats match search', async () => {
    renderGPQueries();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    await user.type(screen.getByPlaceholderText(/search by title/i), 'xyznonexistent');

    expect(screen.getByText('No consultations found')).toBeInTheDocument();
    expect(screen.getByText('Try adjusting your search')).toBeInTheDocument();
  });

  it('shows empty state with create button when no chats exist', async () => {
    server.use(
      http.get('/chats/', () => {
        return HttpResponse.json([]);
      }),
    );

    renderGPQueries();

    await waitFor(() => {
      expect(screen.getByText('No consultations found')).toBeInTheDocument();
    });

    expect(screen.getByText('Create your first consultation to get started')).toBeInTheDocument();
  });

  it('navigates to new query page when button is clicked', async () => {
    renderGPQueries();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('My Consultations')).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /new consultation/i }));

    expect(screen.getByText('New Query Page')).toBeInTheDocument();
  });

  it('shows error message when API fails', async () => {
    server.use(
      http.get('/chats/', () => {
        return HttpResponse.json({ detail: 'Server error' }, { status: 500 });
      }),
    );

    renderGPQueries();

    await waitFor(() => {
      expect(screen.getByText(/failed to load consultations/i)).toBeInTheDocument();
    });
  });

  it('retries loading on error retry button click', async () => {
    let callCount = 0;
    server.use(
      http.get('/chats/', () => {
        callCount++;
        if (callCount === 1) {
          return HttpResponse.json({ detail: 'Error' }, { status: 500 });
        }
        return HttpResponse.json([{ id: 1, title: 'Recovered chat', status: 'open', specialty: null, severity: null, specialist_id: null, assigned_at: null, reviewed_at: null, review_feedback: null, created_at: '2025-01-15T10:00:00Z', user_id: 1 }]);
      }),
    );

    renderGPQueries();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/failed to load/i)).toBeInTheDocument();
    });

    await user.click(screen.getByText('Retry'));

    await waitFor(() => {
      expect(screen.getByText('Recovered chat')).toBeInTheDocument();
    });
  });

  it('deletes a chat when delete button is clicked', async () => {
    renderGPQueries();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    // Find the delete button for the first chat (has title "Delete consultation")
    const deleteButtons = screen.getAllByTitle('Delete consultation');
    await user.click(deleteButtons[0]);

    await waitFor(() => {
      expect(screen.queryByText('Headache consultation')).not.toBeInTheDocument();
    });

    // The second chat should still be there
    expect(screen.getByText('Joint pain assessment')).toBeInTheDocument();
  });

  it('displays status and severity badges', async () => {
    renderGPQueries();

    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    expect(screen.getByText('Open')).toBeInTheDocument();
    expect(screen.getByText('Submitted')).toBeInTheDocument();
    expect(screen.getByText('Medium')).toBeInTheDocument();
    expect(screen.getByText('High')).toBeInTheDocument();
  });
});
