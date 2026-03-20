import { describe, it, expect, vi } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Routes, Route, useLocation } from 'react-router-dom';
import { useEffect } from 'react';
import { server } from '@test/mocks/server';
import { renderWithProviders, seedAuth } from '@test/utils';
import { GPNewQueryPage } from '@/pages/gp/GPNewQueryPage';

function QueriesStub() {
  return <div>Queries List</div>;
}

/** Stub that also exposes the router state so tests can inspect it. */
const captureLocationState = vi.fn();
function QueryDetailStub() {
  const location = useLocation();
  useEffect(() => {
    captureLocationState(location.state);
  }, [location.state]);
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
    const form = screen.getByRole('button', { name: /submit consultation/i }).closest('form');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /submit consultation/i })).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/consultation title/i), 'Test');
    await user.type(screen.getByLabelText(/patient age/i), '42');
    await user.selectOptions(screen.getByLabelText(/sex/i), 'female');
    await user.type(screen.getByLabelText(/clinical question/i), 'What is wrong?');
    fireEvent.submit(form as HTMLFormElement);

    expect(screen.getByText(/please select a specialty before submitting/i)).toBeInTheDocument();
  });

  it('creates a consultation and navigates to detail page with draftMessage', async () => {
    captureLocationState.mockClear();
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
    await waitFor(() => {
      expect(captureLocationState).toHaveBeenLastCalledWith(
        expect.objectContaining({ draftMessage: 'Patient has persistent headaches' }),
      );
    });
  });

  it('keeps the draft message focused on the clinical question when patient age is provided', async () => {
    captureLocationState.mockClear();
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

    await waitFor(() => {
      expect(captureLocationState).toHaveBeenLastCalledWith(
        expect.objectContaining({ draftMessage: 'Headache' }),
      );
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

  it('validates missing age, sex, and specialty requirements', async () => {
    renderNewQuery();
    const user = userEvent.setup();
    const form = screen.getByRole('button', { name: /submit consultation/i }).closest('form');

    await user.type(screen.getByLabelText(/consultation title/i), 'Test');
    await user.type(screen.getByLabelText(/clinical question/i), 'Question');
    await user.selectOptions(screen.getByLabelText(/specialty/i), 'neurology');
    fireEvent.submit(form as HTMLFormElement);
    expect(screen.getByText(/please enter the patient's age/i)).toBeInTheDocument();

    await user.type(screen.getByLabelText(/patient age/i), '42');
    fireEvent.submit(form as HTMLFormElement);
    expect(screen.getByText(/please select the patient's sex/i)).toBeInTheDocument();
  });

  it('validates missing urgency when the severity field is cleared', async () => {
    renderNewQuery();
    const user = userEvent.setup();
    const form = screen.getByRole('button', { name: /submit consultation/i }).closest('form');

    await user.type(screen.getByLabelText(/consultation title/i), 'Test');
    await user.type(screen.getByLabelText(/patient age/i), '42');
    await user.selectOptions(screen.getByLabelText(/sex/i), 'female');
    await user.selectOptions(screen.getByLabelText(/specialty/i), 'neurology');
    fireEvent.change(screen.getByLabelText(/urgency/i), { target: { value: '' } });
    await user.type(screen.getByLabelText(/clinical question/i), 'Question');
    fireEvent.submit(form as HTMLFormElement);

    expect(screen.getByText(/please select urgency/i)).toBeInTheDocument();
  });

  it('uploads files during submission and shows fallback error when creation fails', async () => {
    server.use(
      http.post('/chats/', () => HttpResponse.json({ detail: 'broken' }, { status: 500 })),
    );

    renderNewQuery();
    const user = userEvent.setup({ applyAccept: false });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /submit consultation/i })).toBeInTheDocument();
    });

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(fileInput, new File(['a'], 'one.pdf', { type: 'application/pdf' }));
    expect(screen.getByText('one.pdf')).toBeInTheDocument();

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

  it('uploads and removes attached files before creating a consultation', async () => {
    renderNewQuery();
    const user = userEvent.setup({ applyAccept: false });

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(fileInput, [
      new File(['a'], 'one.pdf', { type: 'application/pdf' }),
      new File(['b'], 'two.txt', { type: 'text/plain' }),
    ]);

    expect(screen.getByText('one.pdf')).toBeInTheDocument();
    expect(screen.getByText('two.txt')).toBeInTheDocument();

    await user.click(screen.getAllByRole('button').find((button) =>
      button.closest('li')?.textContent?.includes('one.pdf'),
    ) as HTMLButtonElement);
    expect(screen.queryByText('one.pdf')).not.toBeInTheDocument();
  });

  it('uses fallback title and omits optional fields when they are blank', async () => {
    captureLocationState.mockClear();
    server.use(
      http.post('/chats/', async ({ request }) => {
        const body = await request.json() as Record<string, unknown>;
        expect(body.title).toBe('New Consultation');
        expect(body.patient_notes).toBeUndefined();
        return HttpResponse.json({ id: 11, ...body });
      }),
    );

    renderNewQuery();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /submit consultation/i })).toBeInTheDocument();
    });

    const form = screen.getByRole('button', { name: /submit consultation/i }).closest('form');
    await user.type(screen.getByLabelText(/patient age/i), '42');
    await user.selectOptions(screen.getByLabelText(/sex/i), 'female');
    await user.selectOptions(screen.getByLabelText(/specialty/i), 'neurology');
    await user.type(screen.getByLabelText(/clinical question/i), 'Question');
    fireEvent.submit(form as HTMLFormElement);

    await waitFor(() => {
      expect(screen.getByText('Query Detail')).toBeInTheDocument();
    });
  });

  it('shows error when attaching oversized files via file input', async () => {
    renderNewQuery();
    const user = userEvent.setup({ applyAccept: false });

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    const oversized = new File(['x'.repeat(4 * 1024 * 1024)], 'huge.pdf', { type: 'application/pdf' });
    await user.upload(fileInput, oversized);

    expect(screen.getByText(/file\(s\) too large.*huge\.pdf.*maximum size is 3 mb/i)).toBeInTheDocument();
  });

  it('ignores cancelled file selections', () => {
    renderNewQuery();
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;

    fireEvent.change(fileInput, { target: { files: null } });

    expect(screen.queryByRole('list')).not.toBeInTheDocument();
  });

  it('uploads attached files on successful submission', async () => {
    captureLocationState.mockClear();
    server.use(
      http.post('/chats/:chatId/files', () =>
        HttpResponse.json({ id: 'file-1', name: 'scan.pdf', size: '1KB', type: 'pdf' })),
    );
    renderNewQuery();
    const user = userEvent.setup({ applyAccept: false });

    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(fileInput, new File(['a'], 'scan.pdf', { type: 'application/pdf' }));

    await user.type(screen.getByLabelText(/consultation title/i), 'Uploaded consultation');
    await user.type(screen.getByLabelText(/patient age/i), '50');
    await user.selectOptions(screen.getByLabelText(/sex/i), 'male');
    await user.selectOptions(screen.getByLabelText(/specialty/i), 'neurology');
    await user.type(screen.getByLabelText(/clinical question/i), 'Please review this scan');
    await user.click(screen.getByRole('button', { name: /submit consultation/i }));

    await waitFor(() => {
      expect(screen.getByText('Query Detail')).toBeInTheDocument();
    });
  });
});
