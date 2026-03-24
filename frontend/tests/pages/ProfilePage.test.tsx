import { describe, it, expect } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { http, HttpResponse } from 'msw';
import { Routes, Route } from 'react-router-dom';
import { ProfilePage } from '@/pages/ProfilePage';
import { renderWithProviders, seedAuth } from '@test/utils';
import { server } from '@test/mocks/server';
import { mockSpecialistUser } from '@test/mocks/handlers';

function renderProfile() {
  seedAuth({ role: 'gp', username: 'Dr GP' });
  return renderWithProviders(
    <Routes>
      <Route path="/profile" element={<ProfilePage />} />
      <Route path="/gp/queries" element={<div>GP Queries</div>} />
      <Route path="/login" element={<div>Login</div>} />
    </Routes>,
    { routes: ['/profile'] },
  );
}

describe('ProfilePage', () => {
  it('loads the profile and shows a no-changes message', async () => {
    renderProfile();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByText(/My Profile/)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /save changes/i }));
    expect(screen.getByText(/No changes to save/i)).toBeInTheDocument();
  });

  it('validates and saves password/profile updates', async () => {
    renderProfile();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByLabelText(/full name/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/^New Password$/i), 'NewPassword1!');
    await user.click(screen.getByRole('button', { name: /save changes/i }));
    expect(screen.getByText(/current password is required/i)).toBeInTheDocument();

    await user.type(screen.getByLabelText(/current password/i), 'oldpass');
    await user.type(screen.getByLabelText(/^Confirm New Password$/i), 'WrongPassword1!');
    await user.click(screen.getByRole('button', { name: /save changes/i }));
    expect(screen.getByText(/new passwords do not match/i)).toBeInTheDocument();

    await user.clear(screen.getByLabelText(/^Confirm New Password$/i));
    await user.type(screen.getByLabelText(/^Confirm New Password$/i), 'NewPassword1!');
    await user.clear(screen.getByLabelText(/full name/i));
    await user.type(screen.getByLabelText(/full name/i), 'Updated User');
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => {
      expect(screen.getByText(/profile updated successfully/i)).toBeInTheDocument();
    });
  });

  it('shows load and save errors', async () => {
    server.use(http.get('/auth/me', () => HttpResponse.json({ detail: 'Nope' }, { status: 500 })));
    renderProfile();

    await waitFor(() => {
      expect(screen.getByText(/failed to load profile/i)).toBeInTheDocument();
    });
  });

  it('validates missing new password and minimum password length', async () => {
    renderProfile();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByLabelText(/current password/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/current password/i), 'oldpass');
    await user.click(screen.getByRole('button', { name: /save changes/i }));
    expect(screen.getAllByText(/new password is required/i).length).toBeGreaterThan(0);

    await user.type(screen.getByLabelText(/^New Password$/i), 'short');
    await user.type(screen.getByLabelText(/^Confirm New Password$/i), 'short');
    await user.click(screen.getByRole('button', { name: /save changes/i }));
    expect(screen.getAllByText(/password must be at least 8 characters/i).length).toBeGreaterThan(0);
  });

  it('rejects weak passwords and overly long names', async () => {
    renderProfile();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByLabelText(/full name/i)).toBeInTheDocument();
    });

    await user.clear(screen.getByLabelText(/full name/i));
    await user.type(screen.getByLabelText(/full name/i), 'A'.repeat(101));
    await user.click(screen.getByRole('button', { name: /save changes/i }));
    expect(screen.getByText(/full name must be 100 characters or fewer/i)).toBeInTheDocument();

    await user.clear(screen.getByLabelText(/full name/i));
    await user.type(screen.getByLabelText(/full name/i), 'Valid User');
    await user.type(screen.getByLabelText(/current password/i), 'oldpass');
    await user.type(screen.getByLabelText(/^New Password$/i), 'password123');
    await user.type(screen.getByLabelText(/^Confirm New Password$/i), 'password123');
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    expect(screen.getByText(/include uppercase, lowercase, a number, and a special character/i)).toBeInTheDocument();
  });

  it('shows specialist specialty field, toggles passwords, and navigates back', async () => {
    server.use(http.get('/auth/me', () => HttpResponse.json(mockSpecialistUser)));
    seedAuth({ role: 'specialist', username: 'Dr Specialist' });
    renderWithProviders(
      <Routes>
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/specialist/queries" element={<div>Specialist Queries</div>} />
        <Route path="/login" element={<div>Login</div>} />
      </Routes>,
      { routes: ['/profile'] },
    );
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByLabelText(/specialty/i)).toBeInTheDocument();
    });

    const toggleButtons = screen.getAllByRole('button').filter((button) =>
      button.className.includes('absolute right-4 top-9'),
    );
    await user.click(toggleButtons[0]);
    await user.click(toggleButtons[1]);
    await user.click(screen.getByRole('button', { name: /show confirm password/i }));
    await user.click(screen.getByRole('button', { name: /back/i }));

    expect(screen.getByText(/specialist queries/i)).toBeInTheDocument();
  });

  it('clears specialty to null for specialists and keeps username fallback when full_name stays empty', async () => {
    server.use(
      http.get('/auth/me', () => HttpResponse.json(mockSpecialistUser)),
      http.patch('/auth/profile', async ({ request }) => {
        const body = await request.json() as { specialty?: string | null };
        expect(body.specialty).toBeNull();
        return HttpResponse.json({
          ...mockSpecialistUser,
          full_name: null,
          specialty: null,
        });
      }),
    );

    seedAuth({ role: 'specialist', username: 'Dr Specialist' });
    renderWithProviders(
      <Routes>
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/specialist/queries" element={<div>Specialist Queries</div>} />
      </Routes>,
      { routes: ['/profile'] },
    );
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByLabelText(/specialty/i)).toBeInTheDocument();
    });

    await user.selectOptions(screen.getByLabelText(/specialty/i), '');
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => {
      expect(screen.getByText(/profile updated successfully/i)).toBeInTheDocument();
    });
  });

  it('loads empty full name and specialty values from a nullable profile', async () => {
    server.use(
      http.get('/auth/me', () =>
        HttpResponse.json({
          ...mockSpecialistUser,
          full_name: null,
          specialty: null,
        })),
    );

    seedAuth({ role: 'specialist' });
    renderWithProviders(
      <Routes>
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/specialist/queries" element={<div>Specialist Queries</div>} />
      </Routes>,
      { routes: ['/profile'] },
    );

    await waitFor(() => {
      expect(screen.getByLabelText(/full name/i)).toHaveValue('');
    });
    expect(screen.getByLabelText(/specialty/i)).toHaveValue('');
  });

  it('shows save errors and gp back navigation path', async () => {
    server.use(
      http.patch('/auth/profile', () => HttpResponse.json({ detail: 'Save failed' }, { status: 500 })),
    );

    renderProfile();
    const user = userEvent.setup();

    await waitFor(() => {
      expect(screen.getByLabelText(/full name/i)).toBeInTheDocument();
    });

    await user.clear(screen.getByLabelText(/full name/i));
    await user.type(screen.getByLabelText(/full name/i), 'Broken Save');
    await user.click(screen.getByRole('button', { name: /save changes/i }));

    await waitFor(() => {
      expect(screen.getByText(/save failed/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /back/i }));
    expect(screen.getByText(/gp queries/i)).toBeInTheDocument();
  });
});
