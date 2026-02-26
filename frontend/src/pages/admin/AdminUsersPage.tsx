import { useState, useEffect } from 'react';
import { Search, Loader2, UserX, Save, X } from 'lucide-react';
import { AdminLayout } from '../../components/AdminLayout';
import { StatusBadge } from '../../components/Badges';
import { adminGetUsers, adminUpdateUser, adminDeactivateUser } from '../../services/api';
import type { UserProfile } from '../../types/api';
import type { UserUpdateAdmin } from '../../types/api';

export function AdminUsersPage() {
  const [users, setUsers] = useState<UserProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [roleFilter, setRoleFilter] = useState('');

  // Edit modal state
  const [editUser, setEditUser] = useState<UserProfile | null>(null);
  const [editForm, setEditForm] = useState<UserUpdateAdmin>({});
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchUsers();
  }, [roleFilter]);

  const fetchUsers = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await adminGetUsers(roleFilter || undefined);
      setUsers(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load users');
    } finally {
      setLoading(false);
    }
  };

  const handleDeactivate = async (userId: number) => {
    if (!confirm('Deactivate this user? They will no longer be able to log in.')) return;
    try {
      const updated = await adminDeactivateUser(userId);
      setUsers(prev => prev.map(u => (u.id === userId ? updated : u)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to deactivate user');
    }
  };

  const openEdit = (user: UserProfile) => {
    setEditUser(user);
    setEditForm({
      full_name: user.full_name,
      specialty: user.specialty,
      role: user.role,
      is_active: user.is_active,
    });
  };

  const handleSave = async () => {
    if (!editUser) return;
    setSaving(true);
    try {
      const updated = await adminUpdateUser(editUser.id, editForm);
      setUsers(prev => prev.map(u => (u.id === editUser.id ? updated : u)));
      setEditUser(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update user');
    } finally {
      setSaving(false);
    }
  };

  const filteredUsers = users.filter(u =>
    (u.full_name || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
    u.email.toLowerCase().includes(searchTerm.toLowerCase()),
  );

  return (
    <AdminLayout>
      <div className="max-w-6xl mx-auto">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">User Management</h1>
            <p className="text-gray-600 mt-1">View, edit, and deactivate user accounts</p>
          </div>
        </div>

        {/* Filters */}
        <div className="bg-white rounded-xl shadow-sm p-4 mb-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
              <input
                type="text"
                placeholder="Search by name or email..."
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                className="w-full pl-12 pr-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent"
              />
            </div>
            <select
              value={roleFilter}
              onChange={e => setRoleFilter(e.target.value)}
              className="px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent bg-white cursor-pointer"
            >
              <option value="">All Roles</option>
              <option value="gp">GP</option>
              <option value="specialist">Specialist</option>
              <option value="admin">Admin</option>
            </select>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            {error}
            <button onClick={fetchUsers} className="ml-3 underline font-medium">Retry</button>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-8 h-8 text-[#005eb8] animate-spin" />
          </div>
        )}

        {/* User Table */}
        {!loading && (
          <div className="bg-white rounded-xl shadow-sm overflow-hidden">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-6 py-3 text-sm font-semibold text-gray-600">Name</th>
                  <th className="text-left px-6 py-3 text-sm font-semibold text-gray-600">Email</th>
                  <th className="text-left px-6 py-3 text-sm font-semibold text-gray-600">Role</th>
                  <th className="text-left px-6 py-3 text-sm font-semibold text-gray-600">Specialty</th>
                  <th className="text-left px-6 py-3 text-sm font-semibold text-gray-600">Status</th>
                  <th className="text-right px-6 py-3 text-sm font-semibold text-gray-600">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filteredUsers.map(user => (
                  <tr key={user.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 text-sm font-medium text-gray-900">
                      {user.full_name || '—'}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600">{user.email}</td>
                    <td className="px-6 py-4">
                      <span className="inline-block px-2.5 py-0.5 text-xs font-medium rounded-full bg-blue-100 text-blue-800 uppercase">
                        {user.role}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600 capitalize">
                      {user.specialty || '—'}
                    </td>
                    <td className="px-6 py-4">
                      {user.is_active ? (
                        <StatusBadge status="approved" />
                      ) : (
                        <StatusBadge status="closed" />
                      )}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => openEdit(user)}
                          className="px-3 py-1.5 text-xs font-medium text-[#005eb8] border border-[#005eb8] rounded-lg hover:bg-[#005eb8] hover:text-white transition-colors"
                        >
                          Edit
                        </button>
                        {user.is_active && (
                          <button
                            onClick={() => handleDeactivate(user.id)}
                            className="p-1.5 text-gray-400 hover:text-red-500 transition-colors"
                            title="Deactivate user"
                          >
                            <UserX className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {filteredUsers.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-6 py-12 text-center text-gray-500">
                      No users found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Edit Modal */}
      {editUser && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-bold text-gray-900">Edit User</h2>
              <button onClick={() => setEditUser(null)} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Full Name</label>
                <input
                  type="text"
                  value={editForm.full_name || ''}
                  onChange={e => setEditForm({ ...editForm, full_name: e.target.value })}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Role</label>
                <select
                  value={editForm.role || ''}
                  onChange={e => setEditForm({ ...editForm, role: e.target.value })}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent bg-white"
                >
                  <option value="gp">GP</option>
                  <option value="specialist">Specialist</option>
                  <option value="admin">Admin</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Specialty</label>
                <input
                  type="text"
                  value={editForm.specialty || ''}
                  onChange={e => setEditForm({ ...editForm, specialty: e.target.value })}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent"
                  placeholder="e.g. neurology, rheumatology"
                />
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="is_active"
                  checked={editForm.is_active ?? true}
                  onChange={e => setEditForm({ ...editForm, is_active: e.target.checked })}
                  className="w-4 h-4 text-[#005eb8] rounded border-gray-300"
                />
                <label htmlFor="is_active" className="text-sm text-gray-700">Active</label>
              </div>
            </div>

            <div className="flex gap-3 justify-end mt-6">
              <button
                onClick={() => setEditUser(null)}
                className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 font-medium hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="inline-flex items-center gap-2 px-4 py-2 bg-[#005eb8] text-white rounded-lg font-medium hover:bg-[#003087] disabled:opacity-50"
              >
                <Save className="w-4 h-4" />
                {saving ? 'Saving…' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}
    </AdminLayout>
  );
}
