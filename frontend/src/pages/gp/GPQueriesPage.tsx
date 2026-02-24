import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Search, Trash2, Loader2 } from 'lucide-react';
import { StatusBadge, SeverityBadge } from '../../components/Badges';
import { Header } from '../../components/Header';
import { useAuth } from '../../contexts/AuthContext';
import { getChats, deleteChat } from '../../services/api';
import type { BackendChat } from '../../types/api';

export function GPQueriesPage() {
  const navigate = useNavigate();
  const { username, logout } = useAuth();
  const [chats, setChats] = useState<BackendChat[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    fetchChats();
  }, []);

  const fetchChats = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await getChats();
      setChats(data);
    } catch {
      setError('Failed to load consultations. Is the backend running?');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (e: React.MouseEvent, chatId: number) => {
    e.stopPropagation();
    if (!confirm('Delete this consultation?')) return;
    try {
      await deleteChat(chatId);
      setChats(prev => prev.filter(c => c.id !== chatId));
    } catch {
      setError('Failed to delete consultation');
    }
  };

  const filteredChats = chats.filter(chat =>
    (chat.title || '').toLowerCase().includes(searchTerm.toLowerCase()),
  );

  const getPreview = (chat: BackendChat) => {
    return `Created ${formatDate(chat.created_at)}`;
  };

  const formatSpecialty = (s: string | null) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : null);

  const formatDate = (iso: string) =>
    new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });

  return (
    <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
      <Header userRole="gp" userName={username || 'GP User'} onLogout={logout} />

      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8">
        {/* Page Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">My Consultations</h1>
            <p className="text-gray-600 mt-1">Manage your AI-assisted clinical consultations</p>
          </div>
          <button
            onClick={() => navigate('/gp/queries/new')}
            className="inline-flex items-center justify-center gap-2 bg-[#005eb8] text-white px-6 py-3 rounded-lg font-medium hover:bg-[#003087] transition-colors"
          >
            <Plus className="w-5 h-5" />
            New Consultation
          </button>
        </div>

        {/* Search */}
        <div className="bg-white rounded-xl shadow-sm p-4 mb-6">
          <div className="relative">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
            <input
              type="text"
              placeholder="Search by title..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full pl-12 pr-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent"
            />
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

        {/* Chat List */}
        {!loading && (
          <div className="space-y-4">
            {filteredChats.length > 0 ? (
              filteredChats.map(chat => (
                <div
                  key={chat.id}
                  onClick={() => navigate(`/gp/query/${chat.id}`)}
                  className="bg-white rounded-xl shadow-sm border border-gray-200 p-4 hover:shadow-md hover:border-[#005eb8] cursor-pointer transition-all"
                >
                  <div className="flex items-start justify-between gap-4 mb-1">
                    <h3 className="font-semibold text-gray-900 text-base sm:text-lg flex-1 min-w-0">
                      {chat.title || 'Untitled Consultation'}
                    </h3>
                    <span className="text-xs text-gray-500 shrink-0">{formatDate(chat.created_at)}</span>
                  </div>
                  <div className="flex items-end justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <p className="text-gray-600 text-sm">{getPreview(chat)}</p>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      {chat.specialty && (
                        <span className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs font-medium">
                          {formatSpecialty(chat.specialty)}
                        </span>
                      )}
                      {chat.severity && <SeverityBadge severity={chat.severity} />}
                      <StatusBadge status={chat.status} />
                      <button
                        onClick={(e) => handleDelete(e, chat.id)}
                        className="p-1.5 text-gray-400 hover:text-red-500 rounded transition-colors"
                        title="Delete consultation"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="bg-white rounded-xl shadow-sm p-12 text-center">
                <div className="text-gray-400 mb-4">
                  <Search className="w-12 h-12 mx-auto" />
                </div>
                <h3 className="text-lg font-medium text-gray-900 mb-2">No consultations found</h3>
                <p className="text-gray-600 mb-6">
                  {searchTerm
                    ? 'Try adjusting your search'
                    : 'Create your first consultation to get started'}
                </p>
                {!searchTerm && (
                  <button
                    onClick={() => navigate('/gp/queries/new')}
                    className="inline-flex items-center gap-2 bg-[#005eb8] text-white px-6 py-3 rounded-lg font-medium hover:bg-[#003087] transition-colors"
                  >
                    <Plus className="w-5 h-5" />
                    New Consultation
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
