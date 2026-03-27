import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Search, Archive, Filter, X } from 'lucide-react';
import { StatusBadge, SeverityBadge } from '../../components/Badges';
import { LoadingSkeleton } from '../../components/LoadingSkeleton';
import { Header } from '../../components/Header';
import { useAuth } from '../../contexts/useAuth';
import { getChats, deleteChat } from '../../services/api';
import type { ChatListFilters } from '../../services/api';
import type { BackendChat } from '../../types/api';
import { ifNotAbortError } from '../../utils/errors';
import { createGpQueriesSearchFetcher } from '../../utils/gpQueries';
import { formatSpecialtyLabel } from '../../utils/specialistQueries';
import { resetTimeoutWithValue } from '../../utils/timers';
import { orFallback } from '../../utils/value';

type TabKey = 'submitted' | 'under_review' | 'closed';

const TAB_STATUSES: Record<TabKey, string[]> = {
  submitted: ['open', 'submitted'],
  under_review: ['assigned', 'reviewing'],
  closed: ['approved', 'rejected'],
};

const SPECIALTY_OPTIONS = ['neurology', 'rheumatology'];

type SortKey = 'created_at' | 'title' | 'specialty' | 'status';
type SortDirection = 'asc' | 'desc';

export function GPQueriesPage() {
  const navigate = useNavigate();
  const { username, logout } = useAuth();
  const [chats, setChats] = useState<BackendChat[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [specialty, setSpecialty] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [tab, setTab] = useState<TabKey>('submitted');
  const [showFilters, setShowFilters] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>('created_at');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestControllerRef = useRef<AbortController | null>(null);

  const hasActiveFilters = !!(specialty || dateFrom || dateTo);

  const buildFilters = useCallback(
    (searchOverride?: string): ChatListFilters => {
      const filters: ChatListFilters = {};
      const s = searchOverride ?? searchTerm;
      if (s) filters.search = s;
      if (specialty) filters.specialty = specialty;
      if (dateFrom) filters.date_from = dateFrom + 'T00:00:00';
      if (dateTo) filters.date_to = dateTo + 'T23:59:59';
      return filters;
    },
    [searchTerm, specialty, dateFrom, dateTo],
  );

  const fetchChats = useCallback(
    async (filters?: ChatListFilters) => {
      // Validate date range before fetching
      if (dateFrom && dateTo && dateFrom > dateTo) {
        setError('Start date must be before end date');
        return;
      }
      requestControllerRef.current?.abort();
      const controller = new AbortController();
      requestControllerRef.current = controller;
      setLoading(true);
      setError('');
      try {
        const data = await getChats(filters ?? buildFilters(), { signal: controller.signal });
        setChats(data);
      } catch (error) {
        ifNotAbortError(error, () => {
          setError('Failed to load consultations. Is the backend running?');
        });
      } finally {
        setLoading(false);
      }
    },
    [buildFilters, dateFrom, dateTo],
  );

  useEffect(() => {
    const debounceTimer = debounceRef.current;
    void fetchChats();
    return () => {
      requestControllerRef.current?.abort();
      if (debounceTimer) {
        clearTimeout(debounceTimer);
      }
    };
  }, [fetchChats]);

  // Refetch when specialty or date filters change
  useEffect(() => {
    void fetchChats(buildFilters());
  }, [buildFilters, fetchChats]);

  const handleSearchChange = (value: string) => {
    setSearchTerm(value);
    const searchFetcher = createGpQueriesSearchFetcher(fetchChats, buildFilters);
    resetTimeoutWithValue(debounceRef, searchFetcher, value, 300);
  };

  /**
   * Archives a consultation with optimistic removal.
   * Restores the previous state on failure so the item reappears.
   */
  const handleArchive = async (e: React.MouseEvent, chatId: number) => {
    e.stopPropagation();
    if (
      !confirm(
        'Permanently remove this consultation from your list?\n\nThis cannot be undone — you will no longer be able to access it. The record is retained internally for audit purposes only.',
      )
    )
      return;
    const prevChats = chats;
    setChats((prev) => prev.filter((c) => c.id !== chatId));
    try {
      await deleteChat(chatId);
    } catch {
      setChats(prevChats);
      setError('Failed to archive consultation');
    }
  };

  const clearFilters = () => {
    setSearchTerm('');
    setSpecialty('');
    setDateFrom('');
    setDateTo('');
    void fetchChats({});
  };

  const tabChats = (key: TabKey) => chats.filter((c) => TAB_STATUSES[key].includes(c.status));

  const filteredChats = [...tabChats(tab)].sort((a, b) => {
    const direction = sortDirection === 'asc' ? 1 : -1;
    if (sortKey === 'created_at') {
      return (new Date(a.created_at).getTime() - new Date(b.created_at).getTime()) * direction;
    }
    const aValue = (a[sortKey] ?? '').toString().toLowerCase();
    const bValue = (b[sortKey] ?? '').toString().toLowerCase();
    return aValue.localeCompare(bValue) * direction;
  });

  const formatDate = (iso: string) =>
    new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });

  const emptyMessage: Record<TabKey, string> = {
    submitted: 'No submitted consultations. Create one to get started.',
    under_review: 'No consultations are currently under specialist review.',
    closed: 'No closed consultations yet.',
  };

  return (
    <div className="min-h-screen bg-[var(--nhs-page-bg)] flex flex-col">
      <Header userRole="gp" userName={orFallback(username, 'GP User')} onLogout={logout} />

      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8">
        {/* Page Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">My Consultations</h1>
            <p className="text-gray-600 mt-1">Manage your AI-assisted clinical consultations</p>
          </div>
          <button
            onClick={() => navigate('/gp/queries/new')}
            className="inline-flex items-center justify-center gap-2 bg-[var(--nhs-blue)] text-white px-6 py-3 rounded-lg font-medium hover:bg-[var(--nhs-dark-blue)] transition-colors"
          >
            <Plus className="w-5 h-5" />
            New Consultation
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 bg-white rounded-lg shadow-sm p-1 mb-6">
          {(
            [
              { key: 'submitted', label: 'Submitted' },
              { key: 'under_review', label: 'Under Review' },
              { key: 'closed', label: 'Closed' },
            ] as { key: TabKey; label: string }[]
          ).map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`flex-1 px-4 py-2.5 rounded-md text-sm font-medium transition-colors ${
                tab === key ? 'bg-[var(--nhs-blue)] text-white' : 'text-gray-600 hover:bg-gray-100'
              }`}
            >
              {label} ({tabChats(key).length})
            </button>
          ))}
        </div>

        {/* Search & Filters */}
        <div className="bg-white rounded-xl shadow-sm p-4 mb-6">
          <div className="flex gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
              <input
                type="text"
                placeholder="Search consultations..."
                value={searchTerm}
                onChange={(e) => handleSearchChange(e.target.value)}
                className="w-full pl-12 pr-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--nhs-blue)] focus:border-transparent"
              />
            </div>
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`inline-flex items-center gap-2 px-4 py-3 border rounded-lg text-sm font-medium transition-colors ${
                showFilters || hasActiveFilters
                  ? 'bg-[var(--nhs-blue)] text-white border-[var(--nhs-blue)]'
                  : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
              }`}
              aria-label="Toggle filters"
            >
              <Filter className="w-4 h-4" />
              Filters
              {hasActiveFilters && (
                <span className="bg-white text-[var(--nhs-blue)] text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center">
                  {[specialty, dateFrom, dateTo].filter(Boolean).length}
                </span>
              )}
            </button>
          </div>

          {/* Expanded filter controls */}
          {showFilters && (
            <div className="mt-4 pt-4 border-t border-gray-200">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
                <div>
                  <label
                    htmlFor="filter-specialty"
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    Specialty
                  </label>
                  <select
                    id="filter-specialty"
                    value={specialty}
                    onChange={(e) => setSpecialty(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--nhs-blue)] focus:border-transparent text-sm"
                  >
                    <option value="">All specialties</option>
                    {SPECIALTY_OPTIONS.map((s) => (
                      <option key={s} value={s}>
                        {s.charAt(0).toUpperCase() + s.slice(1)}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label
                    htmlFor="filter-date-from"
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    From date
                  </label>
                  <input
                    id="filter-date-from"
                    type="date"
                    value={dateFrom}
                    onChange={(e) => setDateFrom(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--nhs-blue)] focus:border-transparent text-sm"
                  />
                </div>
                <div>
                  <label
                    htmlFor="filter-date-to"
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    To date
                  </label>
                  <input
                    id="filter-date-to"
                    type="date"
                    value={dateTo}
                    onChange={(e) => setDateTo(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--nhs-blue)] focus:border-transparent text-sm"
                  />
                </div>
                <div>
                  <label
                    htmlFor="sort-key"
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    Sort by
                  </label>
                  <select
                    id="sort-key"
                    value={sortKey}
                    onChange={(e) => setSortKey(e.target.value as SortKey)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--nhs-blue)] focus:border-transparent text-sm"
                  >
                    <option value="created_at">Created date</option>
                    <option value="title">Title</option>
                    <option value="specialty">Specialty</option>
                    <option value="status">Status</option>
                  </select>
                </div>
                <div>
                  <label
                    htmlFor="sort-direction"
                    className="block text-sm font-medium text-gray-700 mb-1"
                  >
                    Direction
                  </label>
                  <select
                    id="sort-direction"
                    value={sortDirection}
                    onChange={(e) => setSortDirection(e.target.value as SortDirection)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--nhs-blue)] focus:border-transparent text-sm"
                  >
                    <option value="desc">Descending</option>
                    <option value="asc">Ascending</option>
                  </select>
                </div>
              </div>
              {hasActiveFilters && (
                <div className="mt-3 flex justify-end">
                  <button
                    onClick={clearFilters}
                    className="inline-flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900 transition-colors"
                  >
                    <X className="w-4 h-4" />
                    Clear filters
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            {error}
            <button onClick={() => fetchChats()} className="ml-3 underline font-medium">
              Retry
            </button>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="bg-white rounded-xl shadow-sm p-6">
            <LoadingSkeleton lines={5} />
          </div>
        )}

        {/* Chat List */}
        {!loading && (
          <div className="space-y-4">
            {filteredChats.length > 0 ? (
              filteredChats.map((chat) => (
                <div
                  key={chat.id}
                  onClick={() => navigate(`/gp/query/${chat.id}`)}
                  className="bg-white rounded-xl shadow-sm border border-gray-200 p-4 hover:shadow-md hover:border-[var(--nhs-blue)] cursor-pointer transition-all"
                >
                  <div className="flex items-start justify-between gap-4 mb-1">
                    <h3 className="font-semibold text-gray-900 text-base sm:text-lg flex-1 min-w-0">
                      {chat.title || 'Untitled Consultation'}
                    </h3>
                    <span className="text-xs text-gray-500 shrink-0">
                      {formatDate(chat.created_at)}
                    </span>
                  </div>
                  <div className="flex items-end justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <p className="text-gray-600 text-sm">Created {formatDate(chat.created_at)}</p>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      {chat.specialty && (
                        <span className="px-2 py-0.5 bg-gray-100 text-gray-600 rounded text-xs font-medium">
                          {formatSpecialtyLabel(chat.specialty)}
                        </span>
                      )}
                      {chat.severity && <SeverityBadge severity={chat.severity} />}
                      <StatusBadge status={chat.status} />
                      <button
                        onClick={(e) => handleArchive(e, chat.id)}
                        className="p-1.5 text-gray-400 hover:text-amber-600 rounded transition-colors"
                        title="Archive consultation"
                      >
                        <Archive className="w-4 h-4" />
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
                  {searchTerm || hasActiveFilters
                    ? 'Try adjusting your search or filters'
                    : emptyMessage[tab]}
                </p>
                {!searchTerm && !hasActiveFilters && tab === 'submitted' && (
                  <button
                    onClick={() => navigate('/gp/queries/new')}
                    className="inline-flex items-center gap-2 bg-[var(--nhs-blue)] text-white px-6 py-3 rounded-lg font-medium hover:bg-[var(--nhs-dark-blue)] transition-colors"
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
