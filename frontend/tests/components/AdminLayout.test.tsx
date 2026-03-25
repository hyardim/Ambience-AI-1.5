import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { Routes, Route } from 'react-router-dom';
import { AdminLayout } from '@/components/AdminLayout';
import { renderWithProviders, seedAuth } from '@test/utils';

function renderLayout(route = '/admin/users') {
  seedAuth({ role: 'admin', username: 'Admin User' });
  return renderWithProviders(
    <Routes>
      <Route
        path="*"
        element={
          <AdminLayout>
            <div>Admin Content</div>
          </AdminLayout>
        }
      />
    </Routes>,
    { routes: [route] },
  );
}

describe('AdminLayout', () => {
  it('renders children and sidebar nav', () => {
    renderLayout();

    expect(screen.getByText('Admin Content')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /dashboard/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /users/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /guidelines/i })).toBeInTheDocument();
  });

  it('marks the active nav item from the current route', () => {
    renderLayout('/admin/guidelines');

    expect(screen.getByRole('link', { name: /guidelines/i }).className).toContain('bg-[var(--nhs-blue)]');
  });

  it('falls back to default admin name when username is missing', () => {
    seedAuth({ role: 'admin', username: '' });
    renderWithProviders(
      <Routes>
        <Route
          path="*"
          element={
            <AdminLayout>
              <div>Admin Content</div>
            </AdminLayout>
          }
        />
      </Routes>,
      { routes: ['/admin/dashboard'] },
    );

    expect(screen.getAllByText(/^Admin$/).length).toBeGreaterThan(0);
  });
});
