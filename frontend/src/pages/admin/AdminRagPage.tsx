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
            {/* Indexed Documents */}
            <div className="bg-white rounded-xl border border-gray-200 p-5">
              <h2 className="text-sm font-medium text-gray-700 mb-4">Indexed Documents</h2>
              {data.documents.length === 0 ? (
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
                      {data.documents.map((doc) => (
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
