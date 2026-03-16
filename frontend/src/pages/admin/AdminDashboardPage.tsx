import { useEffect, useState } from 'react';
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import { Activity, MessageSquare, Users, ClipboardList, RefreshCw, Loader2 } from 'lucide-react';
import { AdminLayout } from '../../components/AdminLayout';
import { adminGetLogs, adminGetStats } from '../../services/api';
import type { AdminStatsResponse, AuditLogResponse } from '../../types/api';
import { getErrorMessage } from '../../utils/errors';
import { coalesce } from '../../utils/value';

const STATUS_COLOURS: Record<string, string> = {
  open:       '#94a3b8',
  submitted:  '#f59e0b',
  assigned:   '#3b82f6',
  reviewing:  '#8b5cf6',
  approved:   '#22c55e',
  rejected:   '#ef4444',
  closed:     '#6b7280',
  flagged:    '#f97316',
};

const SPECIALTY_COLOURS = ['#005eb8', '#0ea5e9', '#38bdf8', '#7dd3fc', '#bae6fd', '#e0f2fe'];

function StatCard({ label, value, sub, icon: Icon, colour }: {
  label: string; value: string | number; sub?: string;
  icon: React.ElementType; colour: string;
}) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5 flex items-start gap-4">
      <div className={`p-3 rounded-lg ${colour}`}>
        <Icon className="w-5 h-5 text-white" />
      </div>
      <div>
        <p className="text-sm text-gray-500">{label}</p>
        <p className="text-2xl font-bold text-gray-900">{value}</p>
        {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

export default function AdminDashboardPage() {
  const [stats, setStats] = useState<AdminStatsResponse | null>(null);
  const [ragLogs, setRagLogs] = useState<AuditLogResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const fetchStats = async () => {
    setLoading(true);
    setError('');
    try {
      const [statsResponse, ragLogResponse] = await Promise.all([
        adminGetStats(),
        adminGetLogs({ category: 'RAG', limit: 8 }),
      ]);
      setStats(statsResponse);
      setRagLogs(ragLogResponse);
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load stats'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchStats(); }, []);

  const ragPct = stats
    ? stats.total_ai_responses > 0
      ? Math.round((stats.rag_grounded_responses / stats.total_ai_responses) * 100)
      : 0
    : 0;

  const activeUsers = stats
    ? Object.entries(stats.active_users_by_role)
        .filter(([role]) => role !== 'admin')
        .reduce((s, [, n]) => s + n, 0)
    : 0;

  const statusData = stats
    ? Object.entries(stats.chats_by_status).map(([name, value]) => ({ name, value }))
    : [];

  const specialtyData = stats
    ? Object.entries(stats.chats_by_specialty).map(([name, value]) => ({ name, value }))
    : [];

  const formatTimestamp = (iso: string) =>
    new Date(iso).toLocaleString('en-GB', {
      day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
    });

  const activeUsersSummary = stats
    ? `${coalesce(stats.active_users_by_role['gp'], 0)} GPs · ${coalesce(stats.active_users_by_role['specialist'], 0)} specialists`
    : undefined;

  return (
    <AdminLayout>
      <div className="p-6 space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold text-gray-900">Dashboard</h1>
          <button
            onClick={fetchStats}
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

        {loading && !stats ? (
          <div className="flex justify-center py-20">
            <Loader2 className="w-8 h-8 text-[#005eb8] animate-spin" />
          </div>
        ) : stats && (
          <>
            {/* Stat cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard
                label="Total AI Responses"
                value={stats.total_ai_responses}
                icon={MessageSquare}
                colour="bg-[#005eb8]"
              />
              <StatCard
                label="RAG-Grounded"
                value={`${ragPct}%`}
                sub={`${stats.rag_grounded_responses} of ${stats.total_ai_responses} responses`}
                icon={Activity}
                colour="bg-emerald-500"
              />
              <StatCard
                label="Active Consultations"
                value={stats.active_consultations}
                icon={ClipboardList}
                colour="bg-violet-500"
              />
              <StatCard
                label="Active Users"
                value={activeUsers}
                sub={activeUsersSummary}
                icon={Users}
                colour="bg-amber-500"
              />
            </div>

            {/* Bar + Pie row */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Consultations by status */}
              <div className="bg-white rounded-xl border border-gray-200 p-5">
                <h2 className="text-sm font-medium text-gray-700 mb-4">Consultations by Status</h2>
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={statusData} margin={{ top: 0, right: 8, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                    <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                    <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                    <Tooltip />
                    <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                      {statusData.map((entry) => (
                        <Cell key={entry.name} fill={STATUS_COLOURS[entry.name] ?? '#94a3b8'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {/* Consultations by specialty */}
              <div className="bg-white rounded-xl border border-gray-200 p-5">
                <h2 className="text-sm font-medium text-gray-700 mb-4">Consultations by Specialty</h2>
                {specialtyData.length === 0 ? (
                  <p className="text-sm text-gray-400 text-center py-16">No data</p>
                ) : (
                  <ResponsiveContainer width="100%" height={220}>
                    <PieChart>
                      <Pie
                        data={specialtyData}
                        dataKey="value"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        innerRadius={55}
                        outerRadius={85}
                        paddingAngle={3}
                      >
                        {specialtyData.map((entry, i) => (
                          <Cell key={entry.name} fill={SPECIALTY_COLOURS[i % SPECIALTY_COLOURS.length]} />
                        ))}
                      </Pie>
                      <Tooltip />
                      <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 11 }} />
                    </PieChart>
                  </ResponsiveContainer>
                )}
              </div>
            </div>

            {/* Daily AI queries area chart */}
            <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,2fr)_minmax(320px,1fr)] gap-4">
              <div className="bg-white rounded-xl border border-gray-200 p-5">
                <h2 className="text-sm font-medium text-gray-700 mb-4">AI Queries — Last 30 Days</h2>
                {stats.daily_ai_queries.length === 0 ? (
                  <p className="text-sm text-gray-400 text-center py-12">No query data in the last 30 days</p>
                ) : (
                  <ResponsiveContainer width="100%" height={200}>
                    <AreaChart data={stats.daily_ai_queries} margin={{ top: 0, right: 8, left: -20, bottom: 0 }}>
                      <defs>
                        <linearGradient id="aiGradient" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#005eb8" stopOpacity={0.15} />
                          <stop offset="95%" stopColor="#005eb8" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                      <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(d) => d.slice(5)} />
                      <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
                      <Tooltip labelFormatter={(d) => `Date: ${d}`} />
                      <Area
                        type="monotone"
                        dataKey="count"
                        stroke="#005eb8"
                        strokeWidth={2}
                        fill="url(#aiGradient)"
                        name="AI Queries"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                )}
              </div>

              <div className="bg-white rounded-xl border border-gray-200 p-5">
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-sm font-medium text-gray-700">Recent RAG Logs</h2>
                  <span className="text-xs text-gray-400">Last 8 events</span>
                </div>
                {ragLogs.length === 0 ? (
                  <p className="text-sm text-gray-400 text-center py-12">No recent RAG activity</p>
                ) : (
                  <div className="space-y-3">
                    {ragLogs.map((log) => (
                      <div key={log.id} className="rounded-lg border border-gray-200 px-3 py-2">
                        <div className="flex items-center justify-between gap-3">
                          <span className="text-xs font-semibold text-teal-700 bg-teal-50 border border-teal-200 rounded-full px-2 py-0.5">
                            {log.action}
                          </span>
                          <span className="text-xs text-gray-400">{formatTimestamp(log.timestamp)}</span>
                        </div>
                        <p className="mt-2 text-sm text-gray-600 break-words">{log.details || '—'}</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </>
        )}
      </div>
    </AdminLayout>
  );
}
