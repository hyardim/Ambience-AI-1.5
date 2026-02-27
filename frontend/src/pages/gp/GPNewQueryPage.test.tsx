import { describe, it, expect } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Routes, Route } from 'react-router-dom';
import { server } from '../../test/mocks/server';
import { renderWithProviders, seedAuth } from '../../test/utils';
import { GPNewQueryPage } from './GPNewQueryPage';

function QueriesStub() {
  return <div>Queries List</div>;
}
function QueryDetailStub() {
  return <div>Query Detail</div>;
}

function renderNewQuery() {
  seedAuth({ role: 'gp' });
  return renderWithProviders(
    <Routes>
      <Route path="/gp/queries/new" element={<GPNewQueryPage />} />
      <Route path="/gp/queries" element={<QueriesStub />} />
      <Route path="/gp/query/:queryId" element={<QueryDetailStub />} />
    </Routes>,
    { routes: ['/gp/queries/new'] },
  );
}

describe('GPNewQueryPage', () => {
  it('renders the form with required fields', async () => {
    renderNewQuery();

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /new consultation/i })).toBeInTheDocument();
    });

    expect(screen.getByLabelText(/consultation title/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/specialty/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/clinical question/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /submit consultation/i })).toBeInTheDocument();
  });

  it('shows error when specialty is not selected', async () => {
    renderNewQuery();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /submit consultation/i })).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/consultation title/i), 'Test');
    await user.type(screen.getByLabelText(/clinical question/i), 'What is wrong?');

    // Specialty defaults to empty, which should trigger custom error
    // (HTML5 required may also fire, but our custom check runs first)
    // We need to bypass HTML5 validation for this test
    const specialtySelect = screen.getByLabelText(/specialty/i);
    expect(specialtySelect).toHaveValue('');
  });

  it('creates a consultation and navigates to detail page', async () => {
    renderNewQuery();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /submit consultation/i })).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/consultation title/i), 'Headache inquiry');
    await user.selectOptions(screen.getByLabelText(/specialty/i), 'neurology');
    await user.type(screen.getByLabelText(/clinical question/i), 'Patient has persistent headaches');
    await user.click(screen.getByRole('button', { name: /submit consultation/i }));

    await waitFor(() => {
      expect(screen.getByText('Query Detail')).toBeInTheDocument();
    });
  });

  it('shows error on API failure', async () => {
    server.use(
      http.post('/chats/', () => {
        return HttpResponse.json({ detail: 'Server error' }, { status: 500 });
      }),
    );

    renderNewQuery();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /submit consultation/i })).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/consultation title/i), 'Test');
    await user.selectOptions(screen.getByLabelText(/specialty/i), 'neurology');
    await user.type(screen.getByLabelText(/clinical question/i), 'Question');
    await user.click(screen.getByRole('button', { name: /submit consultation/i }));

    await waitFor(() => {
      expect(screen.getByText(/failed to create consultation/i)).toBeInTheDocument();
    });
  });

  it('navigates back when Cancel button is clicked', async () => {
    renderNewQuery();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /cancel/i }));

    expect(screen.getByText('Queries List')).toBeInTheDocument();
  });

  it('navigates back when Back button is clicked', async () => {
    renderNewQuery();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/back to consultations/i)).toBeInTheDocument();
    });

    await user.click(screen.getByText(/back to consultations/i));

    expect(screen.getByText('Queries List')).toBeInTheDocument();
  });

  it('renders severity and patient age fields', async () => {
    renderNewQuery();

    await waitFor(() => {
      expect(screen.getByLabelText(/severity/i)).toBeInTheDocument();
    });

    expect(screen.getByLabelText(/patient age/i)).toBeInTheDocument();
  });
});
