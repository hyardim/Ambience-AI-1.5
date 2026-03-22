import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Routes, Route } from 'react-router-dom';
import { QueryCard } from './QueryCard';
import { renderWithProviders } from '../test/utils';
import type { Query } from '../types';

const query: Query = {
  id: 'q-1',
  title: 'Complex headache case',
  description: 'Patient with recurrent headache and neck pain',
  specialty: 'neurology',
  severity: 'high',
  status: 'pending-review',
  createdAt: new Date('2025-01-01T10:00:00Z'),
  updatedAt: new Date('2025-01-01T10:00:00Z'),
  gpId: 'gp-1',
  gpName: 'Dr GP',
  messages: [
    {
      id: 'm-1',
      senderId: 'gp-1',
      senderName: 'Dr GP',
      senderType: 'gp',
      content: 'Long message to validate preview truncation in query cards '.repeat(4),
      timestamp: new Date('2025-01-01T10:01:00Z'),
    },
  ],
};

describe('QueryCard', () => {
  it('renders specialist-specific metadata', () => {
    renderWithProviders(
      <Routes>
        <Route path="/specialist/queries" element={<QueryCard query={query} userRole="specialist" />} />
      </Routes>,
      { routes: ['/specialist/queries'] },
    );

    expect(screen.getByText(/Complex headache case/i)).toBeInTheDocument();
    expect(screen.getByText(/Neurology/i)).toBeInTheDocument();
    expect(screen.getByText(/From: Dr GP/i)).toBeInTheDocument();
  });

  it('navigates to the detail page when clicked', async () => {
    renderWithProviders(
      <Routes>
        <Route path="/gp/queries" element={<QueryCard query={query} userRole="gp" />} />
        <Route path="/gp/query/:queryId" element={<div>Detail View</div>} />
      </Routes>,
      { routes: ['/gp/queries'] },
    );

    const user = userEvent.setup();
    await user.click(screen.getByText(/Complex headache case/i));

    expect(screen.getByText('Detail View')).toBeInTheDocument();
  });
});
