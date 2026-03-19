import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import { ProtectedRoute } from './components/ProtectedRoute';
import { ErrorBoundary } from './components/ErrorBoundary';

// Auth pages
import { LoginPage } from './pages/auth/LoginPage';
import { RegisterPage } from './pages/auth/RegisterPage';
import { ForgotPasswordPage } from './pages/auth/ForgotPasswordPage';
import { ResetPasswordPage } from './pages/auth/ResetPasswordPage';
import { VerifyEmailPage } from './pages/auth/VerifyEmailPage';
import { ResendVerificationPage } from './pages/auth/ResendVerificationPage';
import { AccessDeniedPage } from './pages/auth/AccessDeniedPage';

// Landing page
import { LandingPage } from './pages/LandingPage';

// GP pages
import { GPQueriesPage } from './pages/gp/GPQueriesPage';
import { GPNewQueryPage } from './pages/gp/GPNewQueryPage';
import { GPQueryDetailPage } from './pages/gp/GPQueryDetailPage';

// Specialist pages
import { SpecialistQueriesPage } from './pages/specialist/SpecialistQueriesPage';
import { SpecialistQueryDetailPage } from './pages/specialist/SpecialistQueryDetailPage';

// Admin pages
import AdminDashboardPage from './pages/admin/AdminDashboardPage';
import { AdminUsersPage } from './pages/admin/AdminUsersPage';
import { AdminChatsPage } from './pages/admin/AdminChatsPage';
import { AdminLogsPage } from './pages/admin/AdminLogsPage';
import { AdminGuidelinesPage } from './pages/admin/AdminGuidelinesPage';

// Profile page
import { ProfilePage } from './pages/ProfilePage';

function App() {
  return (
    <ErrorBoundary>
    <AuthProvider>
      <Router>
        <Routes>
          {/* Landing page */}
          <Route path="/" element={<LandingPage />} />

          {/* Auth routes */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/verify-email" element={<VerifyEmailPage />} />
          <Route path="/resend-verification" element={<ResendVerificationPage />} />
          <Route path="/access-denied" element={<AccessDeniedPage />} />

          {/* GP routes (protected) */}
          <Route path="/gp" element={<Navigate to="/gp/queries" replace />} />
          <Route path="/gp/queries" element={<ProtectedRoute allowedRoles={['gp', 'admin']}><GPQueriesPage /></ProtectedRoute>} />
          <Route path="/gp/queries/new" element={<ProtectedRoute allowedRoles={['gp', 'admin']}><GPNewQueryPage /></ProtectedRoute>} />
          <Route path="/gp/query/:queryId" element={<ProtectedRoute allowedRoles={['gp', 'admin']}><GPQueryDetailPage /></ProtectedRoute>} />

          {/* Specialist routes */}
          <Route path="/specialist" element={<Navigate to="/specialist/queries" replace />} />
          <Route path="/specialist/queries" element={<ProtectedRoute allowedRoles={['specialist', 'admin']}><SpecialistQueriesPage /></ProtectedRoute>} />
          <Route path="/specialist/query/:queryId" element={<ProtectedRoute allowedRoles={['specialist', 'admin']}><SpecialistQueryDetailPage /></ProtectedRoute>} />

          {/* Admin routes */}
          <Route path="/admin" element={<Navigate to="/admin/dashboard" replace />} />
          <Route path="/admin/dashboard" element={<ProtectedRoute allowedRoles={['admin']}><AdminDashboardPage /></ProtectedRoute>} />
          <Route path="/admin/users" element={<ProtectedRoute allowedRoles={['admin']}><AdminUsersPage /></ProtectedRoute>} />
          <Route path="/admin/chats" element={<ProtectedRoute allowedRoles={['admin']}><AdminChatsPage /></ProtectedRoute>} />
          <Route path="/admin/logs" element={<ProtectedRoute allowedRoles={['admin']}><AdminLogsPage /></ProtectedRoute>} />
          <Route path="/admin/guidelines" element={<ProtectedRoute allowedRoles={['admin']}><AdminGuidelinesPage /></ProtectedRoute>} />

          {/* Profile (all authenticated users) */}
          <Route path="/profile" element={<ProtectedRoute allowedRoles={['gp', 'specialist', 'admin']}><ProfilePage /></ProtectedRoute>} />

          {/* Fallback */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Router>
    </AuthProvider>
    </ErrorBoundary>
  );
}

export default App;
