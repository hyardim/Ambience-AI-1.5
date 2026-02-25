import { useState, useEffect } from 'react';
import { Search, Loader2, RefreshCw } from 'lucide-react';
import { AdminLayout } from '../../components/AdminLayout';
import { adminGetLogs } from '../../services/api';
import type { AuditLogResponse } from '../../types/api';

export function AdminLogsPage() {
  const [logs, setLogs] = useState<AuditLogResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // Filters
  const [actionFilter, setActionFilter] = useState('');
  const [userIdFilter, setUserIdFilter] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [limitFilter, setLimitFilter] = useState(200);

  useEffect(() => {
    fetchLogs();
  }, []);

  const fetchLogs = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await adminGetLogs({
        action: actionFilter || undefined,
        user_id: userIdFilter ? Number(userIdFilter) : undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        limit: limitFilter,
      });
      setLogs(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load audit logs');
    } finally {
      setLoading(false);
    }
  };

  const handleApplyFilters = (e: React.FormEvent) => {
    e.preventDefault();
    fetchLogs();
  };

  const formatTimestamp = (iso: string) =>
    new Date(iso).toLocaleString('en-GB', {
      day: '2-digit', month: 'short', year: 'numeric',
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    });

  const ACTION_STYLES: Record<string, string> = {
    LOGIN: 'bg-blue-100 text-blue-800',
    REGISTER: 'bg-blue-100 text-blue-800',
    ASSIGN_SPECIALIST: 'bg-purple-100 text-purple-800',
    REVIEW_APPROVE: 'bg-green-100 text-green-800',
    REVIEW_REJECT: 'bg-red-100 text-red-800',
    SPECIALIST_MESSAGE: 'bg-indigo-100 text-indigo-800',
    SUBMIT_FOR_REVIEW: 'bg-amber-100 text-amber-800',
    CREATE_CHAT: 'bg-gray-100 text-gray-800',
    SEND_MESSAGE: 'bg-gray-100 text-gray-800',
  };

  return (
    <AdminLayout>
      <div className="max-w-6xl mx-auto">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Audit Logs</h1>
            <p className="text-gray-600 mt-1">View system activity and user actions</p>
          </div>
          <button
            onClick={fetchLogs}
            className="inline-flex items-center gap-2 bg-white border border-gray-300 text-gray-700 px-4 py-2 rounded-lg hover:bg-gray-50 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
        </div>

        {/* Filter Controls */}
        <form onSubmit={handleApplyFilters} className="bg-white rounded-xl shadow-sm p-4 mb-6">
          <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
            <div className="relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                placeholder="Action (e.g. LOGIN)"
                value={actionFilter}
                onChange={e => setActionFilter(e.target.value)}
                className="w-full pl-10 pr-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent text-sm"
              />
            </div>
            <input
              type="number"
              placeholder="User ID"
              value={userIdFilter}
              onChange={e => setUserIdFilter(e.target.value)}
              className="px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent text-sm"
            />
            <input
              type="datetime-local"
              value={dateFrom}
              onChange={e => setDateFrom(e.target.value)}
              className="px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent text-sm"
              title="From date"
            />
            <input
              type="datetime-local"
              value={dateTo}
              onChange={e => setDateTo(e.target.value)}
              className="px-4 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent text-sm"
              title="To date"
            />
            <div className="flex gap-2">
              <select
                value={limitFilter}
                onChange={e => setLimitFilter(Number(e.target.value))}
                className="flex-1 px-3 py-2.5 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent bg-white text-sm"
              >
                <option value={50}>50 rows</option>
                <option value={100}>100 rows</option>
                <option value={200}>200 rows</option>
                <option value={500}>500 rows</option>
              </select>
              <button
                type="submit"
                className="px-4 py-2.5 bg-[#005eb8] text-white rounded-lg text-sm font-medium hover:bg-[#003087] transition-colors"
              >
                Apply
              </button>
            </div>
          </div>
        </form>

        {/* Error */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
            {error}
            <button onClick={fetchLogs} className="ml-3 underline font-medium">Retry</button>
          </div>
        )}

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-8 h-8 text-[#005eb8] animate-spin" />
          </div>
        )}

        {/* Logs Table */}
        {!loading && (
          <div className="bg-white rounded-xl shadow-sm overflow-hidden">
            <table className="w-full">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="text-left px-6 py-3 text-sm font-semibold text-gray-600">Timestamp</th>
                  <th className="text-left px-6 py-3 text-sm font-semibold text-gray-600">Action</th>
                  <th className="text-left px-6 py-3 text-sm font-semibold text-gray-600">User</th>
                  <th className="text-left px-6 py-3 text-sm font-semibold text-gray-600">Details</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {logs.map(log => (
                  <tr key={log.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 text-sm text-gray-500 whitespace-nowrap">
                      {formatTimestamp(log.timestamp)}
                    </td>
                    <td className="px-6 py-4">
                      <span
                        className={`inline-block px-2.5 py-0.5 text-xs font-medium rounded-full ${
                          ACTION_STYLES[log.action] || 'bg-gray-100 text-gray-800'
                        }`}
                      >
                        {log.action}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600">
                      {log.user_email || (log.user_id ? `#${log.user_id}` : '—')}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-600 max-w-md truncate" title={log.details || ''}>
                      {log.details || '—'}
                    </td>
                  </tr>
                ))}
                {logs.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-6 py-12 text-center text-gray-500">
                      No audit logs found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AdminLayout>
  );
}
