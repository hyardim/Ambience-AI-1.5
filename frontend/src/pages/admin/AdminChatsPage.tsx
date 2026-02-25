import { useState, useEffect } from 'react';
import { Search, Loader2, Trash2, Save, X, Eye } from 'lucide-react';
import { AdminLayout } from '../../components/AdminLayout';
import { StatusBadge, SeverityBadge } from '../../components/Badges';
import {
  adminGetChats,
  adminUpdateChat,
  adminDeleteChat,
  adminGetChat,
} from '../../services/api';
import type { AdminChatResponse, BackendChatWithMessages, ChatUpdateRequest } from '../../types/api';

export function AdminChatsPage() {
  const [chats, setChats] = useState<AdminChatResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  // Edit modal state
  const [editChat, setEditChat] = useState<AdminChatResponse | null>(null);
  const [editForm, setEditForm] = useState<ChatUpdateRequest>({});
  const [saving, setSaving] = useState(false);

  // Detail modal state
  const [detailChat, setDetailChat] = useState<BackendChatWithMessages | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    fetchChats();
  }, [statusFilter]);

  const fetchChats = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await adminGetChats({
        status: statusFilter || undefined,
      });
      setChats(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load chats');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (chatId: number) => {
    if (!confirm('Delete this chat and all its messages? This cannot be undone.')) return;
    try {
      await adminDeleteChat(chatId);
      setChats(prev => prev.filter(c => c.id !== chatId));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete chat');
    }
  };

  const openEdit = (chat: AdminChatResponse) => {
    setEditChat(chat);
    setEditForm({
      title: chat.title,
      status: chat.status,
      specialty: chat.specialty,
      severity: chat.severity,
    });
  };

  const handleSave = async () => {
    if (!editChat) return;
    setSaving(true);
    try {
      const updated = await adminUpdateChat(editChat.id, editForm);
      setChats(prev => prev.map(c => (c.id === editChat.id ? updated : c)));
      setEditChat(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update chat');
    } finally {
      setSaving(false);
    }
  };

  const openDetail = async (chatId: number) => {
    setDetailLoading(true);
    try {
      const data = await adminGetChat(chatId);
      setDetailChat(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load chat detail');
    } finally {
      setDetailLoading(false);
    }
  };

  const filteredChats = chats.filter(c =>
    (c.title || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
    (c.owner_name || '').toLowerCase().includes(searchTerm.toLowerCase()),
  );

  const formatDate = (iso: string) =>
    new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });

  return (
    <AdminLayout>
      <div className="max-w-6xl mx-auto">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Chat Management</h1>
            <p className="text-gray-600 mt-1">View, edit, and delete consultations</p>
          </div>
        </div>

        {/* Filters */}
        <div className="bg-white rounded-xl shadow-sm p-4 mb-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
              <input
                type="text"
                placeholder="Search by title or owner..."
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                className="w-full pl-12 pr-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent"
              />
            </div>
            <select
              value={statusFilter}
              onChange={e => setStatusFilter(e.target.value)}
              className="px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent bg-white cursor-pointer"
            >
              <option value="">All Status</option>
              <option value="open">Open</option>
              <option value="submitted">Submitted</option>
              <option value="assigned">Assigned</option>
              <option value="reviewing">Reviewing</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
              <option value="closed">Closed</option>
            </select>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            {error}
            <button onClick={fetchChats} className="ml-3 underline font-medium">Retry</button>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-8 h-8 text-[#005eb8] animate-spin" />
          </div>
        )}

        {/* Chat Table */}
        {!loading && (
          <div className="bg-white rounded-xl shadow-sm overflow-hidden">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-6 py-3 text-sm font-semibold text-gray-600">Title</th>
                  <th className="text-left px-6 py-3 text-sm font-semibold text-gray-600">Owner</th>
                  <th className="text-left px-6 py-3 text-sm font-semibold text-gray-600">Specialist</th>
                  <th className="text-left px-6 py-3 text-sm font-semibold text-gray-600">Status</th>
                  <th className="text-left px-6 py-3 text-sm font-semibold text-gray-600">Severity</th>
                  <th className="text-left px-6 py-3 text-sm font-semibold text-gray-600">Created</th>
                  <th className="text-right px-6 py-3 text-sm font-semibold text-gray-600">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filteredChats.map(chat => (
                  <tr key={chat.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 text-sm font-medium text-gray-900 max-w-xs truncate">
                      {chat.title || 'Untitled'}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600">
                      {chat.owner_name || `User #${chat.user_id}`}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600">
                      {chat.specialist_name || '—'}
                    </td>
                    <td className="px-6 py-4">
                      <StatusBadge status={chat.status} />
                    </td>
                    <td className="px-6 py-4">
                      {chat.severity ? <SeverityBadge severity={chat.severity} /> : '—'}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500">
                      {formatDate(chat.created_at)}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <button
                          onClick={() => openDetail(chat.id)}
                          className="p-1.5 text-gray-400 hover:text-[#005eb8] transition-colors"
                          title="View messages"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => openEdit(chat)}
                          className="px-3 py-1.5 text-xs font-medium text-[#005eb8] border border-[#005eb8] rounded-lg hover:bg-[#005eb8] hover:text-white transition-colors"
                        >
                          Edit
                        </button>
                        <button
                          onClick={() => handleDelete(chat.id)}
                          className="p-1.5 text-gray-400 hover:text-red-500 transition-colors"
                          title="Delete chat"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
                {filteredChats.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-6 py-12 text-center text-gray-500">
                      No chats found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Edit Modal */}
      {editChat && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6">
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-xl font-bold text-gray-900">Edit Chat</h2>
              <button onClick={() => setEditChat(null)} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Title</label>
                <input
                  type="text"
                  value={editForm.title || ''}
                  onChange={e => setEditForm({ ...editForm, title: e.target.value })}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
                <select
                  value={editForm.status || ''}
                  onChange={e => setEditForm({ ...editForm, status: e.target.value })}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent bg-white"
                >
                  <option value="open">Open</option>
                  <option value="submitted">Submitted</option>
                  <option value="assigned">Assigned</option>
                  <option value="reviewing">Reviewing</option>
                  <option value="approved">Approved</option>
                  <option value="rejected">Rejected</option>
                  <option value="closed">Closed</option>
                  <option value="flagged">Flagged</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Specialty</label>
                <input
                  type="text"
                  value={editForm.specialty || ''}
                  onChange={e => setEditForm({ ...editForm, specialty: e.target.value })}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent"
                  placeholder="e.g. neurology"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Severity</label>
                <select
                  value={editForm.severity || ''}
                  onChange={e => setEditForm({ ...editForm, severity: e.target.value || null })}
                  className="w-full px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent bg-white"
                >
                  <option value="">None</option>
                  <option value="routine">Routine</option>
                  <option value="urgent">Urgent</option>
                  <option value="emergency">Emergency</option>
                </select>
              </div>
            </div>

            <div className="flex gap-3 justify-end mt-6">
              <button
                onClick={() => setEditChat(null)}
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

      {/* Detail Modal */}
      {(detailChat || detailLoading) && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full max-h-[80vh] flex flex-col overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
              <h2 className="text-xl font-bold text-gray-900">
                {detailChat?.title || 'Loading…'}
              </h2>
              <button
                onClick={() => setDetailChat(null)}
                className="text-gray-400 hover:text-gray-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {detailLoading && (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-6 h-6 text-[#005eb8] animate-spin" />
                </div>
              )}
              {detailChat && detailChat.messages.length === 0 && (
                <p className="text-gray-500 text-center py-8">No messages in this chat.</p>
              )}
              {detailChat?.messages.map(msg => (
                <div
                  key={msg.id}
                  className={`rounded-lg px-4 py-3 ${
                    msg.sender === 'ai'
                      ? 'bg-blue-50 border-l-4 border-[#005eb8]'
                      : msg.sender === 'specialist'
                        ? 'bg-green-50 border-l-4 border-[#007f3b]'
                        : 'bg-gray-50'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-semibold text-gray-500 uppercase">
                      {msg.sender}
                    </span>
                    <span className="text-xs text-gray-400">
                      {new Date(msg.created_at).toLocaleString('en-GB')}
                    </span>
                  </div>
                  <p className="text-sm text-gray-800 whitespace-pre-wrap">{msg.content}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </AdminLayout>
  );
}
