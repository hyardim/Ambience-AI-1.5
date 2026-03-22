import { describe, it, expect } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { server } from '../../test/mocks/server';
import { renderWithProviders, seedAuth } from '../../test/utils';
import { AdminGuidelinesPage } from './AdminGuidelinesPage';

const API = 'http://localhost:8000';

describe('AdminGuidelinesPage', () => {
  it('keeps upload action disabled until a file is selected', async () => {
    seedAuth({ role: 'admin', username: 'Admin User' });
    renderWithProviders(<AdminGuidelinesPage />, { routes: ['/admin/guidelines'] });

    expect(screen.getByRole('button', { name: /Upload & Ingest/i })).toBeDisabled();
  });

  it('shows ingestion summary after successful upload', async () => {
    seedAuth({ role: 'admin', username: 'Admin User' });
    server.use(
      http.post(`${API}/admin/guidelines/upload`, () => {
        return HttpResponse.json({
          filename: 'guideline.pdf',
          source_name: 'NICE',
          total_chunks: 6,
          files_failed: 0,
          embeddings_succeeded: 6,
          embeddings_failed: 0,
          db: { inserted: 6, updated: 0, failed: 0 },
        });
      }),
    );

    renderWithProviders(<AdminGuidelinesPage />, { routes: ['/admin/guidelines'] });

    const user = userEvent.setup();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const pdf = new File(['pdf-content'], 'guideline.pdf', { type: 'application/pdf' });

    await user.upload(input, pdf);
    await user.click(screen.getByRole('button', { name: /Upload & Ingest/i }));

    await waitFor(() => {
      expect(screen.getByText(/Ingestion complete/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/guideline.pdf/i)).toBeInTheDocument();
  });
});
