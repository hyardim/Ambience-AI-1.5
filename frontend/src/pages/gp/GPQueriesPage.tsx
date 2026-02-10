import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Search, Filter } from 'lucide-react';
import { Header } from '../../components/Header';
import { QueryCard } from '../../components/QueryCard';
import { mockQueries, mockGPNotifications } from '../../data/mockData';
import type { QueryStatus, Specialty } from '../../types';

export function GPQueriesPage() {
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState<QueryStatus | 'all'>('all');
  const [specialtyFilter, setSpecialtyFilter] = useState<Specialty | 'all'>('all');

  const filteredQueries = mockQueries.filter(query => {
    const matchesSearch = query.gpName.toLowerCase().includes(searchTerm.toLowerCase()) ||
                         query.title.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesStatus = statusFilter === 'all' || query.status === statusFilter;
    const matchesSpecialty = specialtyFilter === 'all' || query.specialty === specialtyFilter;
    return matchesSearch && matchesStatus && matchesSpecialty;
  });

  return (
    <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
      <Header userRole="gp" userName="Dr. Sarah Johnson" notifications={mockGPNotifications} />
      
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8">
        {/* Page Header */}
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">My Queries</h1>
            <p className="text-gray-600 mt-1">Manage your specialist advice requests</p>
          </div>
          <button
            onClick={() => navigate('/gp/queries/new')}
            className="inline-flex items-center justify-center gap-2 bg-[#005eb8] text-white px-6 py-3 rounded-lg font-medium hover:bg-[#003087] transition-colors"
          >
            <Plus className="w-5 h-5" />
            New Query
          </button>
        </div>

        {/* Filters */}
        <div className="bg-white rounded-xl shadow-sm p-4 mb-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-400" />
              <input
                type="text"
                placeholder="Search by title..."
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
                value={specialtyFilter}
                onChange={(e) => setSpecialtyFilter(e.target.value as Specialty | 'all')}
                className="px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent appearance-none bg-white cursor-pointer"
              >
                <option value="all">All Specialties</option>
                <option value="neurology">Neurology</option>
                <option value="rheumatology">Rheumatology</option>
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
                userRole="gp"
              />
            ))
          ) : (
            <div className="bg-white rounded-xl shadow-sm p-12 text-center">
              <div className="text-gray-400 mb-4">
                <Search className="w-12 h-12 mx-auto" />
              </div>
              <h3 className="text-lg font-medium text-gray-900 mb-2">No queries found</h3>
              <p className="text-gray-600 mb-6">
                {searchTerm || statusFilter !== 'all' || specialtyFilter !== 'all'
                  ? 'Try adjusting your filters'
                  : 'Create your first query to get started'}
              </p>
              {!searchTerm && statusFilter === 'all' && specialtyFilter === 'all' && (
                <button
                  onClick={() => navigate('/gp/queries/new')}
                  className="inline-flex items-center gap-2 bg-[#005eb8] text-white px-6 py-3 rounded-lg font-medium hover:bg-[#003087] transition-colors"
                >
                  <Plus className="w-5 h-5" />
                  New Query
                </button>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}