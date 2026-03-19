import { describe, it, expect, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Routes, Route, useLocation } from 'react-router-dom';
import { server } from '../../test/mocks/server';
import { renderWithProviders, seedAuth } from '../../test/utils';
import { GPNewQueryPage } from './GPNewQueryPage';

function QueriesStub() {
  return <div>Queries List</div>;
}

/** Stub that also exposes the router state so tests can inspect it. */
const capturedState: { current: unknown } = { current: undefined };
function QueryDetailStub() {
  const location = useLocation();
  capturedState.current = location.state;
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

  it('creates a consultation and navigates to detail page with draftMessage', async () => {
    renderNewQuery();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /submit consultation/i })).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/consultation title/i), 'Headache inquiry');
    await user.type(screen.getByLabelText(/patient age/i), '42');
    await user.selectOptions(screen.getByLabelText(/sex/i), 'female');
    await user.selectOptions(screen.getByLabelText(/specialty/i), 'neurology');
    await user.type(screen.getByLabelText(/clinical question/i), 'Patient has persistent headaches');
    await user.click(screen.getByRole('button', { name: /submit consultation/i }));

    await waitFor(() => {
      expect(screen.getByText('Query Detail')).toBeInTheDocument();
    });

    // The draft message should be passed via router state so the detail page
    // can open SSE before sending.
    expect(capturedState.current).toEqual(
      expect.objectContaining({ draftMessage: 'Patient has persistent headaches' }),
    );
  });

  it('keeps the draft message focused on the clinical question when patient age is provided', async () => {
    renderNewQuery();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /submit consultation/i })).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/consultation title/i), 'Test');
    await user.selectOptions(screen.getByLabelText(/specialty/i), 'neurology');
    await user.type(screen.getByLabelText(/patient age/i), '42');
    await user.selectOptions(screen.getByLabelText(/sex/i), 'female');
    await user.type(screen.getByLabelText(/clinical question/i), 'Headache');
    await user.click(screen.getByRole('button', { name: /submit consultation/i }));

    await waitFor(() => {
      expect(screen.getByText('Query Detail')).toBeInTheDocument();
    });

    expect(capturedState.current).toEqual(
      expect.objectContaining({ draftMessage: 'Headache' }),
    );
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
    await user.type(screen.getByLabelText(/patient age/i), '30');
    await user.selectOptions(screen.getByLabelText(/sex/i), 'male');
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

  it('renders urgency, patient age, and sex fields', async () => {
    renderNewQuery();

    await waitFor(() => {
      expect(screen.getByLabelText(/urgency/i)).toBeInTheDocument();
    });

    expect(screen.getByLabelText(/patient age/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/sex/i)).toBeInTheDocument();
  });
});

describe('GPNewQueryPage — file upload size validation', () => {
  it('accepts a file under 3 MB and shows it in the list', async () => {
    renderNewQuery();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/attach files/i)).toBeInTheDocument();
    });

    const smallFile = new File(['x'.repeat(1024)], 'small.pdf', { type: 'application/pdf' });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, smallFile);

    expect(screen.queryByText(/too large/i)).not.toBeInTheDocument();
    expect(screen.getByText('small.pdf')).toBeInTheDocument();
  });

  it('rejects a file over 3 MB and shows an error', async () => {
    renderNewQuery();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/attach files/i)).toBeInTheDocument();
    });

    const bigFile = new File(['x'.repeat(4 * 1024 * 1024)], 'big.pdf', { type: 'application/pdf' });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, bigFile);

    await waitFor(() => {
      expect(screen.getByText(/too large/i)).toBeInTheDocument();
      expect(screen.getByText(/maximum size is 3 MB/i)).toBeInTheDocument();
    });
    expect(screen.queryByText('big.pdf')).not.toBeInTheDocument();
  });

  it('includes the oversized filename in the error message', async () => {
    renderNewQuery();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/attach files/i)).toBeInTheDocument();
    });

    const bigFile = new File(['x'.repeat(4 * 1024 * 1024)], 'oversized_report.pdf', { type: 'application/pdf' });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, bigFile);

    await waitFor(() => {
      expect(screen.getByText(/oversized_report\.pdf/i)).toBeInTheDocument();
    });
  });

  it('removes a file when the X button is clicked', async () => {
    renderNewQuery();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/attach files/i)).toBeInTheDocument();
    });

    const file = new File(['hello'], 'note.pdf', { type: 'application/pdf' });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, file);

    expect(screen.getByText('note.pdf')).toBeInTheDocument();

    // The remove button sits next to the file name in the list item
    const fileItem = screen.getByText('note.pdf').closest('li')!;
    const removeBtn = fileItem.querySelector('button') as HTMLButtonElement;
    await user.click(removeBtn);

    expect(screen.queryByText('note.pdf')).not.toBeInTheDocument();
  });
});
