import { Suspense, lazy } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './contexts/AuthContext';
import { ErrorBoundary } from './components/ErrorBoundary';
import { ProtectedRoute } from './components/ProtectedRoute';
import { LoadingScreen } from './components/LoadingScreen';

const LoginPage = lazy(async () => ({ default: (await import('./pages/auth/LoginPage')).LoginPage }));
const RegisterPage = lazy(async () => ({ default: (await import('./pages/auth/RegisterPage')).RegisterPage }));
const ForgotPasswordPage = lazy(async () => ({ default: (await import('./pages/auth/ForgotPasswordPage')).ForgotPasswordPage }));
const ResetPasswordPage = lazy(async () => ({ default: (await import('./pages/auth/ResetPasswordPage')).ResetPasswordPage }));
const VerifyEmailPage = lazy(async () => ({ default: (await import('./pages/auth/VerifyEmailPage')).VerifyEmailPage }));
const ResendVerificationPage = lazy(async () => ({ default: (await import('./pages/auth/ResendVerificationPage')).ResendVerificationPage }));
const AccessDeniedPage = lazy(async () => ({ default: (await import('./pages/auth/AccessDeniedPage')).AccessDeniedPage }));
const LandingPage = lazy(async () => ({ default: (await import('./pages/LandingPage')).LandingPage }));
const GPQueriesPage = lazy(async () => ({ default: (await import('./pages/gp/GPQueriesPage')).GPQueriesPage }));
const GPNewQueryPage = lazy(async () => ({ default: (await import('./pages/gp/GPNewQueryPage')).GPNewQueryPage }));
const GPQueryDetailPage = lazy(async () => ({ default: (await import('./pages/gp/GPQueryDetailPage')).GPQueryDetailPage }));
const SpecialistQueriesPage = lazy(async () => ({ default: (await import('./pages/specialist/SpecialistQueriesPage')).SpecialistQueriesPage }));
const SpecialistQueryDetailPage = lazy(async () => ({ default: (await import('./pages/specialist/SpecialistQueryDetailPage')).SpecialistQueryDetailPage }));
const AdminDashboardPage = lazy(() => import('./pages/admin/AdminDashboardPage'));
const AdminUsersPage = lazy(async () => ({ default: (await import('./pages/admin/AdminUsersPage')).AdminUsersPage }));
const AdminChatsPage = lazy(async () => ({ default: (await import('./pages/admin/AdminChatsPage')).AdminChatsPage }));
const AdminLogsPage = lazy(async () => ({ default: (await import('./pages/admin/AdminLogsPage')).AdminLogsPage }));
const AdminGuidelinesPage = lazy(async () => ({ default: (await import('./pages/admin/AdminGuidelinesPage')).AdminGuidelinesPage }));
const AdminRagPage = lazy(() => import('./pages/admin/AdminRagPage'));
const ProfilePage = lazy(async () => ({ default: (await import('./pages/ProfilePage')).ProfilePage }));
const NotFoundPage = lazy(async () => ({ default: (await import('./pages/NotFoundPage')).NotFoundPage }));

function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <Router>
          <Suspense fallback={<LoadingScreen />}>
            <Routes>
              <Route path="/" element={<LandingPage />} />
              <Route path="/login" element={<LoginPage />} />
              <Route path="/register" element={<RegisterPage />} />
              <Route path="/forgot-password" element={<ForgotPasswordPage />} />
              <Route path="/reset-password" element={<ResetPasswordPage />} />
              <Route path="/verify-email" element={<VerifyEmailPage />} />
              <Route path="/resend-verification" element={<ResendVerificationPage />} />
              <Route path="/access-denied" element={<AccessDeniedPage />} />

              <Route path="/gp" element={<Navigate to="/gp/queries" replace />} />
              <Route path="/gp/queries" element={<ProtectedRoute allowedRoles={['gp', 'admin']}><GPQueriesPage /></ProtectedRoute>} />
              <Route path="/gp/queries/new" element={<ProtectedRoute allowedRoles={['gp', 'admin']}><GPNewQueryPage /></ProtectedRoute>} />
              <Route path="/gp/query/:queryId" element={<ProtectedRoute allowedRoles={['gp', 'admin']}><GPQueryDetailPage /></ProtectedRoute>} />

              <Route path="/specialist" element={<Navigate to="/specialist/queries" replace />} />
              <Route path="/specialist/queries" element={<ProtectedRoute allowedRoles={['specialist', 'admin']}><SpecialistQueriesPage /></ProtectedRoute>} />
              <Route path="/specialist/query/:queryId" element={<ProtectedRoute allowedRoles={['specialist', 'admin']}><SpecialistQueryDetailPage /></ProtectedRoute>} />

              <Route path="/admin" element={<Navigate to="/admin/dashboard" replace />} />
              <Route path="/admin/dashboard" element={<ProtectedRoute allowedRoles={['admin']}><AdminDashboardPage /></ProtectedRoute>} />
              <Route path="/admin/users" element={<ProtectedRoute allowedRoles={['admin']}><AdminUsersPage /></ProtectedRoute>} />
              <Route path="/admin/chats" element={<ProtectedRoute allowedRoles={['admin']}><AdminChatsPage /></ProtectedRoute>} />
              <Route path="/admin/logs" element={<ProtectedRoute allowedRoles={['admin']}><AdminLogsPage /></ProtectedRoute>} />
              <Route path="/admin/guidelines" element={<ProtectedRoute allowedRoles={['admin']}><AdminGuidelinesPage /></ProtectedRoute>} />
              <Route path="/admin/rag" element={<ProtectedRoute allowedRoles={['admin']}><AdminRagPage /></ProtectedRoute>} />

              <Route path="/profile" element={<ProtectedRoute allowedRoles={['gp', 'specialist', 'admin']}><ProfilePage /></ProtectedRoute>} />
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </Suspense>
        </Router>
      </AuthProvider>
    </ErrorBoundary>
  );
}

export default App;
