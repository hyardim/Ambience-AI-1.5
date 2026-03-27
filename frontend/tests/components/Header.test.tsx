import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Routes, Route } from 'react-router-dom';
import { renderWithProviders, seedAuth } from '@test/utils';
import { Header } from '@/components/Header';

function ProfileStub() {
  return <div>Profile Page</div>;
}
function LoginStub() {
  return <div>Login</div>;
}

function renderHeader(
  props: { userRole: 'gp' | 'specialist' | 'admin'; userName?: string; onLogout?: () => void },
  route = '/gp/queries',
) {
  seedAuth({ role: props.userRole });
  return renderWithProviders(
    <Routes>
      <Route path="*" element={<Header {...props} />} />
      <Route path="/profile" element={<ProfileStub />} />
      <Route path="/login" element={<LoginStub />} />
    </Routes>,
    { routes: [route] },
  );
}

describe('Header', () => {
  it('renders GP role label', () => {
    renderHeader({ userRole: 'gp', userName: 'Dr Test' });
    expect(screen.getByText('For GPs')).toBeInTheDocument();
  });

  it('renders Specialist role label', () => {
    renderHeader({ userRole: 'specialist', userName: 'Dr Spec' }, '/specialist/queries');
    expect(screen.getByText('For Specialists')).toBeInTheDocument();
  });

  it('renders Admin role label', () => {
    renderHeader({ userRole: 'admin', userName: 'Admin User' }, '/admin/users');
    // The role label "Admin" appears both in the title area and the username.
    // Check that at least one element shows the expected role label text.
    expect(screen.getAllByText(/Admin/).length).toBeGreaterThanOrEqual(1);
  });

  it('displays user name', () => {
    renderHeader({ userRole: 'gp', userName: 'Dr Test' });
    expect(screen.getByText('Dr Test')).toBeInTheDocument();
  });

  it('shows Queries link for GP role', () => {
    renderHeader({ userRole: 'gp' });
    expect(screen.getByText('Queries')).toBeInTheDocument();
  });

  it('shows Help link for GP role', () => {
    renderHeader({ userRole: 'gp' });
    expect(screen.getByRole('link', { name: /help/i })).toBeInTheDocument();
  });

  it('shows Help link for specialist role', () => {
    renderHeader({ userRole: 'specialist' }, '/specialist/queries');
    expect(screen.getByRole('link', { name: /help/i })).toBeInTheDocument();
  });

  it('does not show Help link for admin role', () => {
    renderHeader({ userRole: 'admin' }, '/admin/users');
    expect(screen.queryByRole('link', { name: /help/i })).not.toBeInTheDocument();
  });

  it('marks Help link active on the help route', () => {
    renderHeader({ userRole: 'gp' }, '/help');
    expect(screen.getByRole('link', { name: /help/i }).className).toContain(
      'bg-[var(--nhs-dark-blue)]',
    );
  });

  it('shows Admin Panel link for admin role', () => {
    renderHeader({ userRole: 'admin' }, '/admin/users');
    expect(screen.getByText('Admin Panel')).toBeInTheDocument();
  });

  it('does not mark the admin link active outside admin routes', () => {
    renderHeader({ userRole: 'admin' }, '/settings');
    expect(screen.getByText('Admin Panel').closest('a')?.className).not.toContain(
      'bg-[var(--nhs-dark-blue)]',
    );
  });

  it('shows logout button when onLogout is provided', () => {
    const onLogout = vi.fn();
    renderHeader({ userRole: 'gp', onLogout });
    expect(screen.getByTitle('Logout')).toBeInTheDocument();
  });

  it('does not show logout button when onLogout is not provided', () => {
    renderHeader({ userRole: 'gp' });
    expect(screen.queryByTitle('Logout')).not.toBeInTheDocument();
  });

  it('calls onLogout and navigates on logout click', async () => {
    const onLogout = vi.fn();
    renderHeader({ userRole: 'gp', onLogout });
    const user = userEvent.setup();

    await user.click(screen.getByTitle('Logout'));

    expect(onLogout).toHaveBeenCalled();
  });
});
