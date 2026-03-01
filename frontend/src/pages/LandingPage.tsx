import { Link } from 'react-router-dom';
import { NHSLogo } from '../components/NHSLogo';
import { Stethoscope, Users, Shield } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';

function roleLabel(role: 'gp' | 'specialist' | 'admin' | null): string {
  if (role === 'gp') return 'GP';
  if (role === 'specialist') return 'Specialist';
  if (role === 'admin') return 'Admin';
  return 'Unknown';
}

function homeRouteForRole(role: 'gp' | 'specialist' | 'admin' | null): string {
  if (role === 'specialist') return '/specialist/queries';
  if (role === 'admin') return '/admin/users';
  return '/gp/queries';
}

export function LandingPage() {
  const { isAuthenticated, username, role, logout, isLoading } = useAuth();

  return (
    <div className="min-h-screen bg-[#f0f4f5]">
      {/* Header */}
      <header className="bg-[#005eb8] shadow-lg">
        <div className="max-w-6xl mx-auto px-6 sm:px-8 lg:px-12">
          <div className="flex items-center justify-between h-16">
            <NHSLogo />
            <nav className="flex items-center gap-4">
              {isLoading ? (
                <span className="text-white/80 text-sm">Checking session...</span>
              ) : isAuthenticated ? (
                <>
                  <span className="text-white/90 text-sm">
                    Signed in as <span className="font-semibold">{username || 'User'}</span> ({roleLabel(role)})
                  </span>
                  <Link
                    to={homeRouteForRole(role)}
                    className="text-white font-medium hover:text-white/80 transition-colors"
                  >
                    Open Portal
                  </Link>
                  <button
                    type="button"
                    onClick={logout}
                    className="text-white font-medium hover:text-white/80 transition-colors"
                  >
                    Logout
                  </button>
                </>
              ) : (
                <>
                  <Link
                    to="/login"
                    className="text-white font-medium hover:text-white/80 transition-colors"
                  >
                    Login
                  </Link>
                  <Link
                    to="/register"
                    className="text-white font-medium hover:text-white/80 transition-colors"
                  >
                    Register
                  </Link>
                </>
              )}
            </nav>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-6xl mx-auto px-6 sm:px-8 lg:px-12 py-12 sm:py-16 lg:py-20">
        <div className="text-center mb-16">
          <h1 className="text-3xl sm:text-4xl lg:text-5xl font-bold text-gray-900 mb-6 leading-tight">
            NHS Ambience AI 1.5
          </h1>
          <p className="text-lg sm:text-xl text-gray-600 max-w-3xl mx-auto leading-relaxed">
            AI-powered clinical decision support for General Practitioners with specialist oversight
          </p>
        </div>

        <div className={`grid gap-6 lg:gap-8 mb-16 ${role === 'admin' ? 'md:grid-cols-3' : 'md:grid-cols-2'}`}>
          {/* GP Portal */}
          <Link
            to="/gp/queries"
            className="bg-white rounded-2xl shadow-lg p-8 lg:p-10 hover:shadow-xl transition-all duration-300 border-2 border-transparent hover:border-[#005eb8] hover:scale-[1.02] group"
          >
            <div className="flex items-center justify-center w-16 h-16 bg-[#005eb8] rounded-2xl mb-6 group-hover:scale-110 transition-transform">
              <Stethoscope className="w-8 h-8 text-white" />
            </div>
            <h2 className="text-2xl font-bold text-gray-900 mb-3">
              GP Portal
            </h2>
            <p className="text-gray-600 mb-4 leading-relaxed">
              Submit clinical queries, receive AI-powered guidance based on NICE and BSR guidelines, and get specialist input when needed.
            </p>
            <p className="text-sm text-gray-500 mb-3">
              Access: GP or Admin accounts
            </p>
            <span className="text-[#005eb8] font-medium group-hover:underline">
              Enter as GP →
            </span>
          </Link>

          {/* Specialist Portal */}
          <Link
            to="/specialist/queries"
            className="bg-white rounded-2xl shadow-lg p-8 lg:p-10 hover:shadow-xl transition-all duration-300 border-2 border-transparent hover:border-[#005eb8] hover:scale-[1.02] group"
          >
            <div className="flex items-center justify-center w-16 h-16 bg-[#007f3b] rounded-2xl mb-6 group-hover:scale-110 transition-transform">
              <Users className="w-8 h-8 text-white" />
            </div>
            <h2 className="text-2xl font-bold text-gray-900 mb-3">
              Specialist Portal
            </h2>
            <p className="text-gray-600 mb-4 leading-relaxed">
              Review AI-generated responses, provide expert oversight, and ensure accurate clinical guidance for GPs.
            </p>
            <p className="text-sm text-gray-500 mb-3">
              Access: Specialist or Admin accounts
            </p>
            <span className="text-[#005eb8] font-medium group-hover:underline">
              Enter as Specialist →
            </span>
          </Link>

          {/* Admin Portal — only shown when logged in as admin */}
          {role === 'admin' && (
            <Link
              to="/admin/users"
              className="bg-white rounded-2xl shadow-lg p-8 lg:p-10 hover:shadow-xl transition-all duration-300 border-2 border-transparent hover:border-[#da291c] hover:scale-[1.02] group"
            >
              <div className="flex items-center justify-center w-16 h-16 bg-[#da291c] rounded-2xl mb-6 group-hover:scale-110 transition-transform">
                <Shield className="w-8 h-8 text-white" />
              </div>
              <h2 className="text-2xl font-bold text-gray-900 mb-3">
                Admin Panel
              </h2>
              <p className="text-gray-600 mb-4 leading-relaxed">
                Manage users, review all consultations, and audit system activity logs.
              </p>
              <p className="text-sm text-gray-500 mb-3">
                Access: Admin accounts only
              </p>
              <span className="text-[#da291c] font-medium group-hover:underline">
                Open Admin Panel →
              </span>
            </Link>
          )}
        </div>

        {/* Info section */}
        <div className="bg-white rounded-2xl shadow-lg p-8 lg:p-10">
          <h3 className="text-2xl font-bold text-gray-900 mb-8 text-center">
            How it works
          </h3>
          <div className="grid md:grid-cols-3 gap-8 lg:gap-10">
            <div className="text-center">
              <div className="w-12 h-12 bg-[#005eb8] text-white rounded-full flex items-center justify-center mx-auto mb-4 font-bold text-lg">
                1
              </div>
              <h4 className="font-semibold text-gray-900 mb-2 text-lg">GP Submits Query</h4>
              <p className="text-gray-600">
                GPs submit clinical questions with patient details and relevant files
              </p>
            </div>
            <div className="text-center">
              <div className="w-12 h-12 bg-[#005eb8] text-white rounded-full flex items-center justify-center mx-auto mb-4 font-bold text-lg">
                2
              </div>
              <h4 className="font-semibold text-gray-900 mb-2 text-lg">AI Provides Guidance</h4>
              <p className="text-gray-600">
                AI assistant responds with evidence-based recommendations citing NICE guidelines
              </p>
            </div>
            <div className="text-center">
              <div className="w-12 h-12 bg-[#005eb8] text-white rounded-full flex items-center justify-center mx-auto mb-4 font-bold text-lg">
                3
              </div>
              <h4 className="font-semibold text-gray-900 mb-2 text-lg">Specialist Review</h4>
              <p className="text-gray-600">
                Specialists review AI responses, approve or provide additional guidance
              </p>
            </div>
          </div>
        </div>

        {/* Footer links */}
        <div className="mt-12 text-center">
          <div className="flex items-center justify-center gap-6 text-[#005eb8]">
            <a href="https://www.nice.org.uk/guidance/published?sp=on" className="hover:underline font-medium">NICE Guidelines</a>
            <span className="text-gray-300">|</span>
            <a href="https://www.rheumatology.org.uk/guidelines" className="hover:underline font-medium">BSR Guidelines</a>
          </div>
        </div>
      </main>
    </div>
  );
}
