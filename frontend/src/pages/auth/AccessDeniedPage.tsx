import { Link, useLocation } from 'react-router-dom';
import { AlertTriangle } from 'lucide-react';
import { AuthHeader } from '../../components/AuthHeader';
import { useAuth } from '../../contexts/AuthContext';
import type { UserRole } from '../../types';

type AccessDeniedState = {
  from?: string;
  currentRole?: UserRole;
  requiredRoles?: UserRole[];
};

function labelForRole(role: UserRole): string {
  if (role === 'gp') return 'GP';
  if (role === 'specialist') return 'Specialist';
  return 'Admin';
}

export function AccessDeniedPage() {
  const location = useLocation();
  const { logout, role } = useAuth();
  const state = (location.state || {}) as AccessDeniedState;

  const currentRole = state.currentRole || role || null;
  const requiredRoles = state.requiredRoles || [];
  const from = state.from || 'this area';

  return (
    <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
      <AuthHeader />

      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-lg bg-white rounded-2xl shadow-xl p-8 sm:p-10">
          <div className="w-14 h-14 bg-amber-100 rounded-full flex items-center justify-center mx-auto mb-4">
            <AlertTriangle className="w-7 h-7 text-amber-700" />
          </div>

          <h1 className="text-2xl font-bold text-gray-900 text-center mb-3">
            Access Restricted
          </h1>

          <p className="text-gray-600 text-center mb-6">
            You do not have permission to view <span className="font-medium text-gray-800">{from}</span>.
          </p>

          <div className="bg-[#f8fafc] border border-gray-200 rounded-lg p-4 space-y-2 text-sm text-gray-700 mb-8">
            <p>
              <span className="font-semibold">Your role:</span>{' '}
              {currentRole ? labelForRole(currentRole) : 'Not available'}
            </p>
            <p>
              <span className="font-semibold">Required role(s):</span>{' '}
              {requiredRoles.length > 0
                ? requiredRoles.map(labelForRole).join(', ')
                : 'Not specified'}
            </p>
          </div>

          <div className="flex flex-col sm:flex-row gap-3">
            <Link
              to="/"
              className="flex-1 text-center bg-[#005eb8] text-white py-3 px-4 rounded-lg font-medium hover:bg-[#003087] transition-colors"
            >
              Back to Home
            </Link>
            <button
              onClick={logout}
              className="flex-1 border border-gray-300 text-gray-700 py-3 px-4 rounded-lg font-medium hover:bg-gray-50 transition-colors"
            >
              Switch Account
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}