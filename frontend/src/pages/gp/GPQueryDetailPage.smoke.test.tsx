import { describe, it, expect, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Routes, Route } from 'react-router-dom';
import { renderWithProviders, seedAuth } from '../../test/utils';
import { GPQueryDetailPage } from './GPQueryDetailPage';

window.HTMLElement.prototype.scrollIntoView = vi.fn();

function renderDetail(route = '/gp/query/1') {
  seedAuth({ role: 'gp', username: 'Dr GP' });
  return renderWithProviders(
    <Routes>
      <Route path="/gp/query/:queryId" element={<GPQueryDetailPage />} />
      <Route path="/gp/queries" element={<div>GP Queries</div>} />
    </Routes>,
    { routes: [route] },
  );
}

describe('GPQueryDetailPage smoke', () => {
  it('loads consultation and displays messages', async () => {
    renderDetail();

    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: /Back to Consultations/i })).toBeInTheDocument();
  });

  it('navigates back to consultations', async () => {
    renderDetail();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Back to Consultations/i })).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /Back to Consultations/i }));

    expect(screen.getByText('GP Queries')).toBeInTheDocument();
  });
});
