import { describe, it, expect } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { Routes, Route } from 'react-router-dom';
import { HelpPage } from '@/pages/HelpPage';
import { renderWithProviders, seedAuth } from '@test/utils';

function renderHelpPage(role: 'gp' | 'specialist') {
  seedAuth({
    role,
    username: role === 'gp' ? 'Dr GP' : 'Dr Specialist',
    email: role === 'gp' ? 'gp@example.com' : 'specialist@example.com',
  });

  return renderWithProviders(
    <Routes>
      <Route path="/help" element={<HelpPage />} />
      <Route path="/gp/queries" element={<div>GP Queries</div>} />
      <Route path="/specialist/queries" element={<div>Specialist Queries</div>} />
      <Route path="/profile" element={<div>Profile</div>} />
      <Route path="/login" element={<div>Login</div>} />
    </Routes>,
    { routes: ['/help'] },
  );
}

describe('HelpPage', () => {
  it('renders GP workflow guidance and safety limitations', async () => {
    renderHelpPage('gp');

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /help & usage guide/i })).toBeInTheDocument();
    });

    expect(screen.getByRole('heading', { name: /gp workflow/i })).toBeInTheDocument();
    expect(screen.getByText(/step 1: create the consultation/i)).toBeInTheDocument();
    expect(screen.getByText(/start in queries and select new consultation/i)).toBeInTheDocument();
    expect(
      screen.getByText(/enter patient context, specialty, urgency, and a clear clinical question/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/final clinical responsibility remains with the treating gp/i),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /help/i }).className).toContain(
      'bg-[var(--nhs-dark-blue)]',
    );
  });

  it('renders specialist workflow guidance and feature list', async () => {
    renderHelpPage('specialist');

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /specialist workflow/i })).toBeInTheDocument();
    });

    expect(screen.getByText(/step 1: triage incoming consultations/i)).toBeInTheDocument();
    expect(
      screen.getByText(/assign a consultation when you are taking ownership of the review/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/queue and my assigned tabs/i)).toBeInTheDocument();
    expect(screen.getByText(/ai drafts can be incomplete/i)).toBeInTheDocument();
  });

  it('shows shared page sections for features and limitations', async () => {
    renderHelpPage('gp');

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /key features/i })).toBeInTheDocument();
    });

    expect(screen.getByRole('heading', { name: /safety and limitations/i })).toBeInTheDocument();
  });
});
