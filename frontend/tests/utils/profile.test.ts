import { describe, expect, it } from 'vitest';
import { buildProfileUpdatePayload } from '@/utils/profile';

describe('buildProfileUpdatePayload', () => {
  it('builds only the changed fields and password values', () => {
    expect(
      buildProfileUpdatePayload({
        profile: {
          id: 1,
          email: 'a@example.com',
          full_name: 'Old',
          specialty: 'neurology',
          role: 'specialist',
        },
        fullName: 'New',
        specialty: '',
        currentPassword: 'old-pass',
        newPassword: 'NewPassword1!',
      }),
    ).toEqual({
      full_name: 'New',
      specialty: null,
      current_password: 'old-pass',
      new_password: 'NewPassword1!',
    });
  });

  it('returns an empty payload when nothing changed', () => {
    expect(
      buildProfileUpdatePayload({
        profile: {
          id: 1,
          email: 'a@example.com',
          full_name: 'Old',
          specialty: 'neurology',
          role: 'specialist',
        },
        fullName: 'Old',
        specialty: 'neurology',
        currentPassword: '',
        newPassword: '',
      }),
    ).toEqual({});
  });

  it('handles a missing profile when building changes', () => {
    expect(
      buildProfileUpdatePayload({
        profile: null,
        fullName: 'New',
        specialty: '',
        currentPassword: '',
        newPassword: '',
      }),
    ).toEqual({
      full_name: 'New',
    });
  });
});
