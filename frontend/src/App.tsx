import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';

// Auth pages
import { LoginPage } from './pages/auth/LoginPage';
import { RegisterPage } from './pages/auth/RegisterPage';
import { ResetPasswordPage } from './pages/auth/ResetPasswordPage';

// Landing page
import { LandingPage } from './pages/LandingPage';

// GP pages
import { GPQueriesPage } from './pages/gp/GPQueriesPage';
import { GPNewQueryPage } from './pages/gp/GPNewQueryPage';
import { GPQueryDetailPage } from './pages/gp/GPQueryDetailPage';

// Specialist pages
import { SpecialistQueriesPage } from './pages/specialist/SpecialistQueriesPage';
import { SpecialistQueryDetailPage } from './pages/specialist/SpecialistQueryDetailPage';

function App() {
  return (
    <Router>
      <Routes>
        {/* Landing page */}
        <Route path="/" element={<LandingPage />} />

        {/* Auth routes */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/reset-password" element={<ResetPasswordPage />} />

        {/* GP routes */}
        <Route path="/gp" element={<Navigate to="/gp/queries" replace />} />
        <Route path="/gp/queries" element={<GPQueriesPage />} />
        <Route path="/gp/queries/new" element={<GPNewQueryPage />} />
        <Route path="/gp/query/:queryId" element={<GPQueryDetailPage />} />

        {/* Specialist routes */}
        <Route path="/specialist" element={<Navigate to="/specialist/queries" replace />} />
        <Route path="/specialist/queries" element={<SpecialistQueriesPage />} />
        <Route path="/specialist/query/:queryId" element={<SpecialistQueryDetailPage />} />

        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Router>
  );
}

export default App;
