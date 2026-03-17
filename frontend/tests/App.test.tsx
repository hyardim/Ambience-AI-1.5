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

  it('renders the auth routes', async () => {
    const cases = [
      ['/login', /login to your account/i],
      ['/register', /create your account/i],
      ['/reset-password', /reset your password/i],
      ['/access-denied', /access restricted/i],
    ] as const;

    for (const [route, text] of cases) {
      window.history.pushState({}, '', route);
      const { unmount } = render(<App />);
      await waitFor(() => {
        expect(screen.getByText(text)).toBeInTheDocument();
      });
      unmount();
    }
  });

  it('renders gp routes for authenticated users', async () => {
    const cases = [
      ['/gp/queries', /my consultations/i],
      ['/gp/queries/new', /new consultation/i],
      ['/gp/query/1', /headache consultation/i],
    ] as const;

    for (const [route, text] of cases) {
      seedAuth({ role: 'gp', username: 'GP User' });
      window.history.pushState({}, '', route);
      const { unmount } = render(<App />);
      await waitFor(() => {
        expect(screen.getByText(text)).toBeInTheDocument();
      });
      unmount();
    }
  });

  it('renders specialist routes for authenticated users', async () => {
    const cases = [
      ['/specialist/queries', /queries for review/i],
      ['/specialist/query/1', /headache consultation/i],
    ] as const;

    for (const [route, text] of cases) {
      seedAuth({ role: 'specialist', username: 'Specialist User' });
      window.history.pushState({}, '', route);
      const { unmount } = render(<App />);
      await waitFor(() => {
        expect(screen.getByText(text)).toBeInTheDocument();
      });
      unmount();
    }
  });

  it('renders the remaining admin and shared routes', async () => {
    const cases = [
      ['/admin/users', () => screen.getByRole('heading', { name: /user management/i })],
      ['/admin/chats', () => screen.getByRole('heading', { name: /chat management/i })],
      ['/admin/logs', () => screen.getByRole('heading', { name: /audit logs/i })],
      ['/admin/guidelines', () => screen.getByRole('heading', { name: /guidelines/i })],
      ['/profile', () => screen.getByRole('heading', { name: /my profile/i })],
    ] as const;

    for (const [route, query] of cases) {
      seedAuth({ role: 'admin', username: 'Admin User' });
      window.history.pushState({}, '', route);
      const { unmount } = render(<App />);
      await waitFor(() => {
        expect(query()).toBeInTheDocument();
      });
      unmount();
    }
  });
});
