import { describe, it, expect, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Routes, Route } from 'react-router-dom';
import { renderWithProviders, seedAuth } from '../../test/utils';
import { SpecialistQueryDetailPage } from './SpecialistQueryDetailPage';

window.HTMLElement.prototype.scrollIntoView = vi.fn();

function renderDetail(route = '/specialist/query/1') {
  seedAuth({ role: 'specialist', username: 'Dr Specialist' });
  return renderWithProviders(
    <Routes>
      <Route path="/specialist/query/:queryId" element={<SpecialistQueryDetailPage />} />
      <Route path="/specialist/queries" element={<div>Specialist Queries</div>} />
    </Routes>,
    { routes: [route] },
  );
}

describe('SpecialistQueryDetailPage smoke', () => {
  it('loads detail and action hints', async () => {
    renderDetail();

    await waitFor(() => {
      expect(screen.getByText('Headache consultation')).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: /Back to Queries/i })).toBeInTheDocument();
  });

  it('navigates back to specialist queue', async () => {
    renderDetail();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Back to Queries/i })).toBeInTheDocument();
    });

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /Back to Queries/i }));

    expect(screen.getByText('Specialist Queries')).toBeInTheDocument();
  });
});
