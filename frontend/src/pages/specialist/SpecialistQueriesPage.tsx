import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Filter, Clock, Loader2, RefreshCw } from 'lucide-react';
import { Header } from '../../components/Header';
import { StatusBadge, SeverityBadge } from '../../components/Badges';
import { useAuth } from '../../contexts/AuthContext';
import { getSpecialistQueue, getAssignedChats } from '../../services/api';
import type { BackendChat } from '../../types/api';

type TabKey = 'queue' | 'assigned';

export function SpecialistQueriesPage() {
  const navigate = useNavigate();
  const { username, logout } = useAuth();

  const [tab, setTab] = useState<TabKey>('queue');
  const [queueChats, setQueueChats] = useState<BackendChat[]>([]);
  const [assignedChats, setAssignedChatsState] = useState<BackendChat[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [severityFilter, setSeverityFilter] = useState<string>('all');

  useEffect(() => {
    fetchAll();
  }, []);

  const fetchAll = async () => {
    setLoading(true);
    setError('');
    try {
      const [queue, assigned] = await Promise.all([
        getSpecialistQueue(),
        getAssignedChats(),
      ]);
      setQueueChats(queue);
      setAssignedChatsState(assigned);
    } catch {
      setError('Failed to load chats. Is the backend running?');
    } finally {
      setLoading(false);
    }
  };

  const currentList = tab === 'queue' ? queueChats : assignedChats;

  const filteredChats = currentList.filter(chat => {
    const matchesSearch =
      (chat.title || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
      (chat.specialty || '').toLowerCase().includes(searchTerm.toLowerCase());
    const matchesStatus = statusFilter === 'all' || chat.status === statusFilter;
    const matchesSeverity = severityFilter === 'all' || chat.severity === severityFilter;
    return matchesSearch && matchesStatus && matchesSeverity;
  });

  const pendingCount = queueChats.length + assignedChats.filter(c => ['assigned', 'reviewing'].includes(c.status)).length;

  const formatSpecialty = (s: string | null) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : '—');
  const formatDate = (iso: string) =>
    new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });

  return (
    <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
      <Header userRole="specialist" userName={username || 'Specialist User'} onLogout={logout} />

      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8">
        {/* Page Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Queries for Review</h1>
            <p className="text-gray-600 mt-1">Review and approve AI-generated responses</p>
          </div>
          <div className="flex items-center gap-3">
            {pendingCount > 0 && (
              <div className="inline-flex items-center gap-2 bg-amber-100 text-amber-800 px-4 py-2 rounded-lg">
                <Clock className="w-5 h-5" />
                <span className="font-medium">{pendingCount} pending</span>
              </div>
            )}
            <button
              onClick={fetchAll}
              className="inline-flex items-center gap-2 bg-white border border-gray-300 text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-50 transition-colors"
            >
              <RefreshCw className="w-4 h-4" />
              Refresh
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 bg-white rounded-lg shadow-sm p-1 mb-6">
          <button
            onClick={() => setTab('queue')}
            className={`flex-1 px-4 py-2.5 rounded-md text-sm font-medium transition-colors ${
              tab === 'queue'
                ? 'bg-[#005eb8] text-white'
                : 'text-gray-600 hover:bg-gray-100'
            }`}
          >
            Queue ({queueChats.length})
          </button>
          <button
            onClick={() => setTab('assigned')}
            className={`flex-1 px-4 py-2.5 rounded-md text-sm font-medium transition-colors ${
              tab === 'assigned'
                ? 'bg-[#005eb8] text-white'
                : 'text-gray-600 hover:bg-gray-100'
            }`}
          >
            My Assigned ({assignedChats.length})
          </button>
        </div>

        {/* Filters */}
        <div className="bg-white rounded-xl shadow-sm p-4 mb-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
              <input
                type="text"
                placeholder="Search by title or specialty..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-12 pr-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent"
              />
            </div>
            <div className="flex gap-4">
              <div className="relative">
                <Filter className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="pl-10 pr-8 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent appearance-none bg-white cursor-pointer"
                >
                  <option value="all">All Status</option>
                  <option value="submitted">Submitted</option>
                  <option value="assigned">Assigned</option>
                  <option value="reviewing">Reviewing</option>
                  <option value="approved">Approved</option>
                  <option value="rejected">Rejected</option>
                </select>
              </div>
              <select
                value={severityFilter}
                onChange={(e) => setSeverityFilter(e.target.value)}
                className="px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent appearance-none bg-white cursor-pointer"
              >
                <option value="all">All Severity</option>
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="urgent">Urgent</option>
              </select>
            </div>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            {error}
            <button onClick={fetchAll} className="ml-3 underline font-medium">Retry</button>
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
                  onClick={() => navigate(`/specialist/query/${chat.id}`)}
                  className="bg-white rounded-xl shadow-sm border border-gray-200 p-4 hover:shadow-md hover:border-[#005eb8] cursor-pointer transition-all"
                >
                  <div className="flex items-start justify-between gap-4 mb-1">
                    <h3 className="font-semibold text-gray-900 text-base sm:text-lg flex-1 min-w-0">
                      {chat.title || 'Untitled Consultation'}
                    </h3>
                    {chat.specialty && (
                      <span className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs font-medium shrink-0">
                        {formatSpecialty(chat.specialty)}
                      </span>
                    )}
                  </div>
                  <div className="flex items-end justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <p className="text-gray-500 text-sm">
                        Created {formatDate(chat.created_at)}
                        {chat.assigned_at && ` · Assigned ${formatDate(chat.assigned_at)}`}
                      </p>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      {chat.severity && <SeverityBadge severity={chat.severity} />}
                      <StatusBadge status={chat.status} />
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="bg-white rounded-xl shadow-sm p-12 text-center">
                <div className="text-gray-400 mb-4">
                  <Search className="w-12 h-12 mx-auto" />
                </div>
                <h3 className="text-lg font-medium text-gray-900 mb-2">No queries found</h3>
                <p className="text-gray-600">
                  {searchTerm || statusFilter !== 'all' || severityFilter !== 'all'
                    ? 'Try adjusting your filters'
                    : tab === 'queue'
                      ? 'No chats awaiting review right now'
                      : 'You have no assigned chats'}
                </p>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
