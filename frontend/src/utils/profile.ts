import type { ProfileUpdateRequest, UserProfile } from '../types/api';

export function buildProfileUpdatePayload(params: {
  profile: UserProfile | null;
  fullName: string;
  specialty: string;
  currentPassword: string;
  newPassword: string;
}) {
  const { profile, fullName, specialty, currentPassword, newPassword } = params;
  const payload: ProfileUpdateRequest = {};

  if (fullName !== (profile?.full_name ?? '')) {
    payload.full_name = fullName;
  }
  if (specialty !== (profile?.specialty ?? '')) {
    payload.specialty = specialty || null;
  }
  if (newPassword) {
    payload.current_password = currentPassword;
    payload.new_password = newPassword;
  }

  return payload;
}
