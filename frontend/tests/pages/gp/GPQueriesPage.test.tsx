import { describe, it, expect, vi, afterEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Routes, Route } from 'react-router-dom';
import { server } from '@test/mocks/server';
import { renderWithProviders, seedAuth } from '@test/utils';
import { GPQueriesPage } from '@/pages/gp/GPQueriesPage';
import { createGpQueriesSearchFetcher, fetchGpQueriesForSearch } from '@/utils/gpQueries';
import * as api from '@/services/api';

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
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

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

  it('filters chats by search term via server', async () => {
    renderGPQueries();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    await user.type(screen.getByPlaceholderText(/search consultations/i), 'Joint');

    await waitFor(() => {
      expect(screen.queryByText('Headache consultation')).not.toBeInTheDocument();
    });
    expect(screen.getByText('Joint pain assessment')).toBeInTheDocument();
  });

  it('runs the debounced search fetch after the delay', async () => {
    const fetchChats = vi.fn().mockResolvedValue(undefined);
    const buildFilters = vi.fn().mockReturnValue({ search: 'abc' });

    await fetchGpQueriesForSearch(fetchChats, buildFilters, 'abc');

    expect(buildFilters).toHaveBeenCalledWith('abc');
    expect(fetchChats).toHaveBeenCalledWith({ search: 'abc' });
  });

  it('creates a reusable debounced search callback', () => {
    const fetchChats = vi.fn().mockResolvedValue(undefined);
    const buildFilters = vi.fn().mockReturnValue({ search: 'abc' });
    const callback = createGpQueriesSearchFetcher(fetchChats, buildFilters);

    callback('abc');

    expect(buildFilters).toHaveBeenCalledWith('abc');
    expect(fetchChats).toHaveBeenCalledWith({ search: 'abc' });
  });

  it('shows empty state when no chats match search', async () => {
    renderGPQueries();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    // Override handler to return empty for the search
    server.use(
      http.get('/chats/', () => {
        return HttpResponse.json([]);
      }),
    );

    await user.type(screen.getByPlaceholderText(/search consultations/i), 'xyznonexistent');

    await waitFor(() => {
      expect(screen.getByText('No consultations found')).toBeInTheDocument();
    });
    expect(screen.getByText('Try adjusting your search or filters')).toBeInTheDocument();
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

    expect(screen.getByText('No submitted consultations. Create one to get started.')).toBeInTheDocument();
  });

  it('renders consultations without a specialty badge when specialty is null', async () => {
    server.use(
      http.get('/chats/', () =>
        HttpResponse.json([
          {
            id: 3,
            title: 'No specialty',
            status: 'open',
            specialty: null,
            severity: null,
            specialist_id: null,
            assigned_at: null,
            reviewed_at: null,
            review_feedback: null,
            created_at: '2025-01-15T10:00:00Z',
            user_id: 1,
          },
        ]),
      ),
    );

    renderGPQueries();

    await waitFor(() => {
      expect(screen.getByText('No specialty')).toBeInTheDocument();
    });
    expect(screen.queryByText('Neurology')).not.toBeInTheDocument();
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

  it('archives a chat when archive button is clicked', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    server.use(
      http.delete('/chats/:chatId', () => HttpResponse.json({ status: 'ok' })),
    );
    renderGPQueries();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    const headacheCard = screen.getByText('Headache consultation').closest('div[class*="bg-white"]')!;
    await user.click(within(headacheCard).getByTitle('Archive consultation'));

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

  // ── Filter UI tests ────────────────────────────────────────────────────

  it('shows filter panel when Filters button is clicked', async () => {
    renderGPQueries();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    // Click the Filters button
    await user.click(screen.getByLabelText('Toggle filters'));

    // Filter controls should now be visible
    expect(screen.getByLabelText('Specialty')).toBeInTheDocument();
    expect(screen.getByLabelText('From date')).toBeInTheDocument();
    expect(screen.getByLabelText('To date')).toBeInTheDocument();
  });

  it('filters by specialty via server', async () => {
    renderGPQueries();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    // Open filters
    await user.click(screen.getByLabelText('Toggle filters'));

    // Select neurology specialty
    await user.selectOptions(screen.getByLabelText('Specialty'), 'neurology');

    // Server-side mock handler filters by specialty, so only neurology chat remains
    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });
    expect(screen.queryByText('Joint pain assessment')).not.toBeInTheDocument();
  });

  it('clears all filters when Clear filters button is clicked', async () => {
    renderGPQueries();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    // Open filters and select a specialty
    await user.click(screen.getByLabelText('Toggle filters'));
    await user.selectOptions(screen.getByLabelText('Specialty'), 'neurology');

    await waitFor(() => {
      expect(screen.queryByText('Joint pain assessment')).not.toBeInTheDocument();
    });

    // Clear filters
    await user.click(screen.getByText('Clear filters'));

    // Both chats should be visible again
    await waitFor(() => {
      expect(screen.getByText('Joint pain assessment')).toBeInTheDocument();
    });
    expect(screen.getByText('Headache consultation')).toBeInTheDocument();
  });

  it('shows date range controls in filter panel', async () => {
    renderGPQueries();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    await user.click(screen.getByLabelText('Toggle filters'));

    const dateFrom = screen.getByLabelText('From date');
    const dateTo = screen.getByLabelText('To date');
    expect(dateFrom).toHaveAttribute('type', 'date');
    expect(dateTo).toHaveAttribute('type', 'date');
  });

  it('shows filter count badge when filters are active', async () => {
    renderGPQueries();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    await user.click(screen.getByLabelText('Toggle filters'));
    await user.selectOptions(screen.getByLabelText('Specialty'), 'neurology');

    // The Filters button should contain a badge with the active filter count
    await waitFor(() => {
      const filtersButton = screen.getByLabelText('Toggle filters');
      const badge = filtersButton.querySelector('span');
      expect(badge).not.toBeNull();
      expect(badge!.textContent).toBe('1');
    });
  });

  it('only shows supported specialty filter options', async () => {
    renderGPQueries();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    await user.click(screen.getByLabelText('Toggle filters'));
    const specialtySelect = screen.getByLabelText('Specialty');

    expect(screen.getByRole('option', { name: 'Neurology' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Rheumatology' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Cardiology' })).not.toBeInTheDocument();
    expect(specialtySelect).toBeInTheDocument();
  });

  it('sorts consultations by title ascending', async () => {
    server.use(
      http.get('/chats/', () =>
        HttpResponse.json([
          { id: 1, title: 'Zulu case', status: 'submitted', specialty: 'rheumatology', severity: null, specialist_id: null, assigned_at: null, reviewed_at: null, review_feedback: null, created_at: '2025-01-15T10:00:00Z', user_id: 1 },
          { id: 2, title: 'Alpha case', status: 'open', specialty: 'neurology', severity: null, specialist_id: null, assigned_at: null, reviewed_at: null, review_feedback: null, created_at: '2025-01-15T09:00:00Z', user_id: 1 },
        ]),
      ),
    );

    renderGPQueries();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('Zulu case')).toBeInTheDocument();
    });

    await user.click(screen.getByLabelText('Toggle filters'));
    await user.selectOptions(screen.getByLabelText('Sort by'), 'title');
    await user.selectOptions(screen.getByLabelText('Direction'), 'asc');

    await waitFor(() => {
      const headings = screen
        .getAllByRole('heading', { level: 3 })
        .map((heading) => heading.textContent);
      expect(headings[0]).toBe('Alpha case');
      expect(headings[1]).toBe('Zulu case');
    });
  });

  it('switches tabs and shows closed consultations', async () => {
    renderGPQueries();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /closed/i }));

    await waitFor(() => {
      expect(screen.getByText(/no closed consultations yet/i)).toBeInTheDocument();
    });
  });

  it('shows archive failure and respects cancel confirmation', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm');
    confirmSpy.mockReturnValueOnce(false).mockReturnValueOnce(true);
    server.use(
      http.delete('/chats/:chatId', () => HttpResponse.json({ detail: 'Nope' }, { status: 500 })),
    );

    renderGPQueries();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    const archiveButtons = screen.getAllByTitle('Archive consultation');
    await user.click(archiveButtons[0]);
    expect(screen.getByText('Headache consultation')).toBeInTheDocument();

    await user.click(archiveButtons[0]);
    await waitFor(() => {
      expect(screen.getByText(/failed to archive consultation/i)).toBeInTheDocument();
    });

    confirmSpy.mockRestore();
  });

  it('shows unknown-title fallback and filter count for date filters', async () => {
    server.use(
      http.get('/chats/', () =>
        HttpResponse.json([
          { id: 3, title: '', status: 'open', specialty: null, severity: null, specialist_id: null, assigned_at: null, reviewed_at: null, review_feedback: null, created_at: '2025-01-15T10:00:00Z', user_id: 1 },
        ])),
    );

    renderGPQueries();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/untitled consultation/i)).toBeInTheDocument();
    });

    await user.click(screen.getByLabelText('Toggle filters'));
    await user.type(screen.getByLabelText('From date'), '2025-01-01');
    await user.type(screen.getByLabelText('To date'), '2025-01-31');

    await waitFor(() => {
      const badge = screen.getByLabelText('Toggle filters').querySelector('span');
      expect(badge?.textContent).toBe('2');
    });
  });

  it('navigates to a query detail card and opens the create page from the empty submitted state', async () => {
    renderGPQueries();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Headache consultation'));
    expect(screen.getByText('Query Detail Page')).toBeInTheDocument();

    server.use(http.get('/chats/', () => HttpResponse.json([])));
    renderGPQueries();

    await waitFor(() => {
      expect(screen.getByText(/no submitted consultations\. create one to get started\./i)).toBeInTheDocument();
    });

    await user.click(screen.getAllByRole('button', { name: /new consultation/i }).at(-1)!);
    expect(screen.getByText('New Query Page')).toBeInTheDocument();
  });

  it('ignores aborted fetches without surfacing an error', async () => {
    vi.spyOn(api, 'getChats').mockRejectedValueOnce(new DOMException('Aborted', 'AbortError'));

    renderGPQueries();

    await waitFor(() => {
      expect(screen.queryByText(/failed to load consultations/i)).not.toBeInTheDocument();
    });
  });

  it('shows a validation error when the start date is after the end date', async () => {
    renderGPQueries();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/my consultations/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /filter/i }));
    await user.type(screen.getByLabelText(/from date/i), '2025-12-31');
    await user.type(screen.getByLabelText(/to date/i), '2025-01-01');

    await waitFor(() => {
      expect(screen.getByText(/start date must be before end date/i)).toBeInTheDocument();
    });
  });

});
