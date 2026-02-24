import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Loader2, Save, Eye, EyeOff, CheckCircle } from 'lucide-react';
import { Header } from '../components/Header';
import { useAuth } from '../contexts/AuthContext';
import { getProfile, updateProfile } from '../services/api';
import type { UserProfile, ProfileUpdateRequest } from '../types/api';

export function ProfilePage() {
  const navigate = useNavigate();
  const { username, role, logout } = useAuth();

  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  // Form fields
  const [fullName, setFullName] = useState('');
  const [specialty, setSpecialty] = useState('');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showCurrentPw, setShowCurrentPw] = useState(false);
  const [showNewPw, setShowNewPw] = useState(false);

  useEffect(() => {
    loadProfile();
  }, []);

  const loadProfile = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await getProfile();
      setProfile(data);
      setFullName(data.full_name || '');
      setSpecialty(data.specialty || '');
    } catch {
      setError('Failed to load profile');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccessMsg('');

    // Validate password fields
    if (newPassword && !currentPassword) {
      setError('Current password is required to set a new password');
      return;
    }
    if (newPassword && newPassword !== confirmPassword) {
      setError('New passwords do not match');
      return;
    }
    if (newPassword && newPassword.length < 6) {
      setError('New password must be at least 6 characters');
      return;
    }

    const payload: ProfileUpdateRequest = {};

    // Only include changed fields
    if (fullName !== (profile?.full_name || '')) {
      payload.full_name = fullName;
    }
    if (specialty !== (profile?.specialty || '')) {
      payload.specialty = specialty || null;
    }
    if (newPassword) {
      payload.current_password = currentPassword;
      payload.new_password = newPassword;
    }

    // Nothing to update
    if (Object.keys(payload).length === 0) {
      setSuccessMsg('No changes to save');
      return;
    }

    setSaving(true);
    try {
      const updated = await updateProfile(payload);
      setProfile(updated);
      setFullName(updated.full_name || '');
      setSpecialty(updated.specialty || '');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');

      // Update localStorage so Header name is in sync
      if (updated.full_name) {
        localStorage.setItem('username', updated.full_name);
      }

      setSuccessMsg('Profile updated successfully');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update profile');
    } finally {
      setSaving(false);
    }
  };

  const backPath = role === 'specialist' ? '/specialist/queries' : '/gp/queries';

  if (loading) {
    return (
      <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
        <Header userRole={role || 'gp'} userName={username || 'User'} onLogout={logout} />
        <main className="flex-1 flex items-center justify-center">
          <Loader2 className="w-8 h-8 text-[#005eb8] animate-spin" />
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
      <Header userRole={role || 'gp'} userName={username || 'User'} onLogout={logout} />

      <main className="flex-1 max-w-2xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8">
        {/* Back */}
        <button
          onClick={() => navigate(backPath)}
          className="inline-flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-6"
        >
          <ArrowLeft className="w-5 h-5" />
          Back
        </button>

        <div className="bg-white rounded-xl shadow-sm p-6 sm:p-8">
          <h1 className="text-2xl font-bold text-gray-900 mb-6">My Profile</h1>

          {/* Read-only info */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8 pb-6 border-b border-gray-200">
            <div>
              <label className="block text-sm font-medium text-gray-500 mb-1">Email</label>
              <p className="text-gray-900">{profile?.email}</p>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-500 mb-1">Role</label>
              <p className="text-gray-900 capitalize">{profile?.role}</p>
            </div>
          </div>

          <form onSubmit={handleSave} className="space-y-6">
            {/* Full name */}
            <div>
              <label htmlFor="fullName" className="block text-sm font-medium text-gray-700 mb-1">
                Full Name
              </label>
              <input
                id="fullName"
                type="text"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent"
                placeholder="Dr. Jane Smith"
              />
            </div>

            {/* Specialty (visible for specialists) */}
            {profile?.role === 'specialist' && (
              <div>
                <label htmlFor="specialty" className="block text-sm font-medium text-gray-700 mb-1">
                  Specialty
                </label>
                <select
                  id="specialty"
                  value={specialty}
                  onChange={(e) => setSpecialty(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent bg-white"
                >
                  <option value="">— Select —</option>
                  <option value="neurology">Neurology</option>
                  <option value="rheumatology">Rheumatology</option>
                </select>
              </div>
            )}

            {/* Password change section */}
            <fieldset className="pt-4 border-t border-gray-200">
              <legend className="text-sm font-medium text-gray-700 mb-4">Change Password</legend>

              <div className="space-y-4">
                {/* Current password */}
                <div className="relative">
                  <label htmlFor="currentPassword" className="block text-sm text-gray-600 mb-1">
                    Current Password
                  </label>
                  <input
                    id="currentPassword"
                    type={showCurrentPw ? 'text' : 'password'}
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    className="w-full px-4 py-3 pr-12 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent"
                    placeholder="Enter current password"
                    autoComplete="current-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowCurrentPw(!showCurrentPw)}
                    className="absolute right-4 top-9 text-gray-400 hover:text-gray-600"
                  >
                    {showCurrentPw ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>

                {/* New password */}
                <div className="relative">
                  <label htmlFor="newPassword" className="block text-sm text-gray-600 mb-1">
                    New Password
                  </label>
                  <input
                    id="newPassword"
                    type={showNewPw ? 'text' : 'password'}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    className="w-full px-4 py-3 pr-12 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent"
                    placeholder="Enter new password"
                    autoComplete="new-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowNewPw(!showNewPw)}
                    className="absolute right-4 top-9 text-gray-400 hover:text-gray-600"
                  >
                    {showNewPw ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>

                {/* Confirm new password */}
                <div>
                  <label htmlFor="confirmPassword" className="block text-sm text-gray-600 mb-1">
                    Confirm New Password
                  </label>
                  <input
                    id="confirmPassword"
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent"
                    placeholder="Re-enter new password"
                    autoComplete="new-password"
                  />
                </div>
              </div>
            </fieldset>

            {/* Feedback */}
            {error && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                {error}
              </div>
            )}
            {successMsg && (
              <div className="p-3 bg-green-50 border border-green-200 rounded-lg text-green-700 text-sm flex items-center gap-2">
                <CheckCircle className="w-4 h-4" />
                {successMsg}
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={saving}
              className="inline-flex items-center gap-2 bg-[#005eb8] text-white px-6 py-3 rounded-lg font-medium hover:bg-[#003087] transition-colors disabled:opacity-50"
            >
              {saving ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <Save className="w-5 h-5" />
              )}
              {saving ? 'Saving…' : 'Save Changes'}
            </button>
          </form>
        </div>
      </main>
    </div>
  );
}
