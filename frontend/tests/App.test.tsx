import { describe, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import App from '@/App';
import { seedAuth } from '@test/utils';

describe('App', () => {
  it('renders the landing page on root route', async () => {
    window.history.pushState({}, '', '/');
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/NHS Ambience AI 1.5/)).toBeInTheDocument();
    });
  });

  it('redirects authenticated admin users to the admin dashboard route', async () => {
    seedAuth({ role: 'admin', username: 'Admin User' });
    window.history.pushState({}, '', '/admin');
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/Total AI Responses/i)).toBeInTheDocument();
    });
  });

  it('falls back unknown routes to the landing page', async () => {
    window.history.pushState({}, '', '/does-not-exist');
    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/AI-powered clinical decision support/i)).toBeInTheDocument();
    });
  });
});
