import { describe, it, expect } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Routes, Route } from 'react-router-dom';
import { AdminGuidelinesPage } from '@/pages/admin/AdminGuidelinesPage';
import { renderWithProviders, seedAuth } from '@test/utils';
import { server } from '@test/mocks/server';

function renderPage() {
  seedAuth({ role: 'admin', username: 'Admin' });
  return renderWithProviders(
    <Routes>
      <Route path="/admin/guidelines" element={<AdminGuidelinesPage />} />
      <Route path="/login" element={<div>Login</div>} />
    </Routes>,
    { routes: ['/admin/guidelines'] },
  );
}

describe('AdminGuidelinesPage', () => {
  it('validates file selection and type', async () => {
    const { container } = renderPage();
    const user = userEvent.setup({ applyAccept: false });
    const form = screen.getByRole('button', { name: /upload & ingest/i }).closest('form');

    fireEvent.submit(form as HTMLFormElement);
    expect(screen.getByText(/please select a pdf file/i)).toBeInTheDocument();

    expect(screen.getByRole('button', { name: /upload & ingest/i })).toBeDisabled();

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(['hello'], 'notes.txt', { type: 'text/plain' }));
    await user.click(screen.getByRole('button', { name: /upload & ingest/i }));
    expect(screen.getByText(/only pdf files are supported/i)).toBeInTheDocument();
  });

  it('uploads a guideline and shows the result summary', async () => {
    const { container } = renderPage();
    const user = userEvent.setup({ applyAccept: false });

    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(['%PDF'], 'guideline.pdf', { type: 'application/pdf' }));
    await user.selectOptions(screen.getByRole('combobox'), 'NICE_NEURO');
    await user.click(screen.getByRole('button', { name: /upload & ingest/i }));

    await waitFor(() => {
      expect(screen.getByText(/ingestion complete/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/guideline\.pdf/i)).toBeInTheDocument();
    expect(screen.getByText(/indexed under/i)).toBeInTheDocument();
  });

  it('shows upload errors', async () => {
    server.use(
      http.post('/admin/guidelines/upload', () =>
        HttpResponse.json({ detail: 'Upload failed' }, { status: 500 })),
    );

    const { container } = renderPage();
    const user = userEvent.setup();

    await user.upload(
      container.querySelector('input[type="file"]') as HTMLInputElement,
      new File(['%PDF'], 'guideline.pdf', { type: 'application/pdf' }),
    );
    await user.click(screen.getByRole('button', { name: /upload & ingest/i }));

    await waitFor(() => {
      expect(screen.getByText(/upload failed/i)).toBeInTheDocument();
    });
  });

  it('shows warning counts when ingestion has partial failures', async () => {
    server.use(
      http.post('/admin/guidelines/upload', () =>
        HttpResponse.json({
          filename: 'guideline.pdf',
          source_name: 'NICE',
          total_chunks: 10,
          files_failed: 1,
          embeddings_succeeded: 8,
          embeddings_failed: 2,
          db: { inserted: 6, updated: 1, failed: 1 },
        })),
    );

    const { container } = renderPage();
    const user = userEvent.setup({ applyAccept: false });

    await user.upload(
      container.querySelector('input[type="file"]') as HTMLInputElement,
      new File(['%PDF'], 'guideline.pdf', { type: 'application/pdf' }),
    );
    await user.click(screen.getByRole('button', { name: /upload & ingest/i }));

    await waitFor(() => {
      expect(screen.getByText(/warning: 1 file\(s\) failed, 2 embedding\(s\) failed, 1 db write\(s\) failed/i)).toBeInTheDocument();
    });
  });
});
