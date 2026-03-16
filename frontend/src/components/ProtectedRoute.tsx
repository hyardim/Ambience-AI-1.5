import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../contexts/useAuth';
import type { UserRole } from '../types';

interface ProtectedRouteProps {
  children: React.ReactNode;
  allowedRoles?: UserRole[];
}

export function ProtectedRoute({ children, allowedRoles }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading, role } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[var(--nhs-page-bg)] flex items-center justify-center">
        <div className="text-gray-600 text-lg">Loading...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (allowedRoles && role && !allowedRoles.includes(role)) {
    return (
      <Navigate
        to="/access-denied"
        replace
        state={{
          from: location.pathname,
          currentRole: role,
          requiredRoles: allowedRoles,
        }}
      />
    );
  }

  return <>{children}</>;
}
