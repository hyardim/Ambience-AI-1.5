import { useState } from 'react';
import { Search, Filter, Clock } from 'lucide-react';
import { Header } from '../../components/Header';
import { QueryCard } from '../../components/QueryCard';
import { mockQueries, mockSpecialistNotifications } from '../../data/mockData';
import type { QueryStatus, Severity } from '../../types';
import { useAuth } from '../../contexts/AuthContext';

export function SpecialistQueriesPage() {
  const { username, logout } = useAuth();
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<QueryStatus | 'all'>('all');
  const [severityFilter, setSeverityFilter] = useState<Severity | 'all'>('all');

  // All queries are relevant for specialist review
  const specialistQueries = mockQueries;

  const filteredQueries = specialistQueries.filter(query => {
    const matchesSearch = query.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         query.gpName.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesStatus = statusFilter === 'all' || query.status === statusFilter;
    const matchesSeverity = severityFilter === 'all' || query.severity === severityFilter;
    return matchesSearch && matchesStatus && matchesSeverity;
  });

  const pendingReviewCount = specialistQueries.filter(q => q.status === 'active' || q.status === 'pending-review').length;

  return (
    <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
      <Header userRole="specialist" userName={username || 'Specialist User'} notifications={mockSpecialistNotifications} onLogout={logout} />
      
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8">
        {/* Page Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Queries for Review</h1>
            <p className="text-gray-600 mt-1">Review and approve AI-generated responses</p>
          </div>
          {pendingReviewCount > 0 && (
            <div className="inline-flex items-center gap-2 bg-amber-100 text-amber-800 px-4 py-2 rounded-lg">
              <Clock className="w-5 h-5" />
              <span className="font-medium">{pendingReviewCount} pending review</span>
            </div>
          )}
        </div>

        {/* Filters */}
        <div className="bg-white rounded-xl shadow-sm p-4 mb-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
              <input
                type="text"
                placeholder="Search by GP or title..."
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
                  onChange={(e) => setStatusFilter(e.target.value as QueryStatus | 'all')}
                  className="pl-10 pr-8 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent appearance-none bg-white cursor-pointer"
                >
                  <option value="all">All Status</option>
                  <option value="active">Active</option>
                  <option value="pending-review">Pending Review</option>
                  <option value="resolved">Resolved</option>
                </select>
              </div>
              <select
                value={severityFilter}
                onChange={(e) => setSeverityFilter(e.target.value as Severity | 'all')}
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

        {/* Query List */}
        <div className="space-y-4">
          {filteredQueries.length > 0 ? (
            filteredQueries.map(query => (
              <QueryCard
                key={query.id}
                query={query}
                userRole="specialist"
              />
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
                  : 'No queries awaiting review'}
              </p>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}