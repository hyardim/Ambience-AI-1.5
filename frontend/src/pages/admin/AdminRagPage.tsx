import { useEffect, useRef, useState } from 'react';
import { RefreshCw, Loader2, CheckCircle, XCircle, AlertTriangle, Clock, Activity } from 'lucide-react';
import { AdminLayout } from '../../components/AdminLayout';
import { adminGetRagStatus } from '../../services/api';
import type { RagStatusResponse } from '../../types/api';
import { getErrorMessage, ifNotAbortError } from '../../utils/errors';

const formatTimestamp = (iso: string | null) => {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
};

function HealthBadge({ status }: { status: string }) {
  if (status === 'healthy' || status === 'ready') {
    return (
      <span className="inline-flex items-center gap-1.5 text-sm font-medium text-green-700 bg-green-50 border border-green-200 rounded-full px-3 py-1">
        <CheckCircle className="w-4 h-4" />
        {status === 'ready' ? 'Ready' : 'Healthy'}
      </span>
    );
  }
  if (status === 'degraded') {
    return (
      <span className="inline-flex items-center gap-1.5 text-sm font-medium text-amber-700 bg-amber-50 border border-amber-200 rounded-full px-3 py-1">
        <AlertTriangle className="w-4 h-4" />
        Degraded
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 text-sm font-medium text-red-700 bg-red-50 border border-red-200 rounded-full px-3 py-1">
      <XCircle className="w-4 h-4" />
      {status}
    </span>
  );
}

export default function AdminRagPage() {
  const [data, setData] = useState<RagStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [sortKey, setSortKey] = useState<'source_name' | 'chunk_count' | 'latest_ingestion'>('latest_ingestion');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const requestControllerRef = useRef<AbortController | null>(null);

  const fetchStatus = async () => {
    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    setLoading(true);
    setError('');
    try {
      const response = await adminGetRagStatus({ signal: controller.signal });
      setData(response);
    } catch (err) {
      ifNotAbortError(err, () => {
        setError(getErrorMessage(err, 'Failed to load RAG status'));
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchStatus();
    return () => {
      requestControllerRef.current?.abort();
    };
  }, []);

  const sourceOptions = Array.from(new Set(data?.documents.map((doc) => doc.source_name).filter(Boolean) ?? [])).sort();
  const visibleDocuments = [...(data?.documents ?? [])]
    .filter((doc) => {
      const matchesSearch =
        !searchTerm ||
        doc.doc_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
        doc.source_name.toLowerCase().includes(searchTerm.toLowerCase());
      const matchesSource = sourceFilter === 'all' || doc.source_name === sourceFilter;
      return matchesSearch && matchesSource;
    })
    .sort((a, b) => {
      const direction = sortDirection === 'asc' ? 1 : -1;
      if (sortKey === 'chunk_count') {
        return (a.chunk_count - b.chunk_count) * direction;
      }
      if (sortKey === 'latest_ingestion') {
        const aTime = a.latest_ingestion ? new Date(a.latest_ingestion).getTime() : 0;
        const bTime = b.latest_ingestion ? new Date(b.latest_ingestion).getTime() : 0;
        return (aTime - bTime) * direction;
      }
      return a.source_name.localeCompare(b.source_name) * direction;
    });

  return (
    <AdminLayout>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <h1 className="text-xl font-semibold text-gray-900">RAG Pipeline</h1>
            {data && <HealthBadge status={data.service_status} />}
          </div>
          <button
            onClick={fetchStatus}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>

        {error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
            {error}
          </div>
        )}

        {loading && !data ? (
          <div className="flex justify-center py-20">
            <Loader2 className="w-8 h-8 text-[var(--nhs-blue)] animate-spin" />
          </div>
        ) : data && (
          <>
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <div className="md:col-span-2">
                  <label htmlFor="rag-search" className="block text-sm font-medium text-gray-700 mb-1">Search</label>
                  <input
                    id="rag-search"
                    type="text"
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    placeholder="Search by document ID or source..."
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--nhs-blue)] focus:border-transparent text-sm"
                  />
                </div>
                <div>
                  <label htmlFor="rag-source" className="block text-sm font-medium text-gray-700 mb-1">Source</label>
                  <select
                    id="rag-source"
                    value={sourceFilter}
                    onChange={(e) => setSourceFilter(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--nhs-blue)] focus:border-transparent text-sm"
                  >
                    <option value="all">All sources</option>
                    {sourceOptions.map((source) => (
                      <option key={source} value={source}>{source}</option>
                    ))}
                  </select>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label htmlFor="rag-sort-key" className="block text-sm font-medium text-gray-700 mb-1">Sort by</label>
                    <select
                      id="rag-sort-key"
                      value={sortKey}
                      onChange={(e) => setSortKey(e.target.value as 'source_name' | 'chunk_count' | 'latest_ingestion')}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--nhs-blue)] focus:border-transparent text-sm"
                    >
                      <option value="latest_ingestion">Last ingested</option>
                      <option value="source_name">Source</option>
                      <option value="chunk_count">Chunks</option>
                    </select>
                  </div>
                  <div>
                    <label htmlFor="rag-sort-direction" className="block text-sm font-medium text-gray-700 mb-1">Direction</label>
                    <select
                      id="rag-sort-direction"
                      value={sortDirection}
                      onChange={(e) => setSortDirection(e.target.value as 'asc' | 'desc')}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--nhs-blue)] focus:border-transparent text-sm"
                    >
                      <option value="desc">Descending</option>
                      <option value="asc">Ascending</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>

            {/* Indexed Documents */}
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <h2 className="text-sm font-medium text-gray-700 mb-4">Indexed Documents</h2>
              {visibleDocuments.length === 0 ? (
                <p className="text-sm text-gray-400 text-center py-12">No indexed documents</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-gray-200 text-left text-gray-500">
                        <th className="pb-2 pr-4 font-medium">Document ID</th>
                        <th className="pb-2 pr-4 font-medium">Source</th>
                        <th className="pb-2 pr-4 font-medium text-right">Chunks</th>
                        <th className="pb-2 font-medium">Last Ingested</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {visibleDocuments.map((doc) => (
                        <tr key={doc.doc_id} className="text-gray-700">
                          <td className="py-2.5 pr-4 font-mono text-xs">{doc.doc_id}</td>
                          <td className="py-2.5 pr-4">{doc.source_name}</td>
                          <td className="py-2.5 pr-4 text-right">{doc.chunk_count}</td>
                          <td className="py-2.5 text-gray-500 text-xs">{formatTimestamp(doc.latest_ingestion)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* Job Counts */}
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <h2 className="text-sm font-medium text-gray-700 mb-4">Ingestion Jobs</h2>
              {!data.jobs ? (
                <p className="text-sm text-gray-400 text-center py-8">No job data available</p>
              ) : (
                <div className="grid grid-cols-3 gap-4">
                  <div className="flex items-center gap-3 p-4 bg-amber-50 border border-amber-100 rounded-lg">
                    <Clock className="w-5 h-5 text-amber-600 shrink-0" />
                    <div>
                      <p className="text-2xl font-bold text-amber-700">{data.jobs.pending}</p>
                      <p className="text-xs text-amber-600">Pending</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 p-4 bg-blue-50 border border-blue-100 rounded-lg">
                    <Activity className="w-5 h-5 text-blue-600 shrink-0" />
                    <div>
                      <p className="text-2xl font-bold text-blue-700">{data.jobs.running}</p>
                      <p className="text-xs text-blue-600">Running</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 p-4 bg-red-50 border border-red-100 rounded-lg">
                    <XCircle className="w-5 h-5 text-red-600 shrink-0" />
                    <div>
                      <p className="text-2xl font-bold text-red-700">{data.jobs.failed}</p>
                      <p className="text-xs text-red-600">Failed</p>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </AdminLayout>
  );
}
