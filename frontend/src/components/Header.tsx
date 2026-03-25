import { Link, useLocation, useNavigate } from 'react-router-dom';
import { User, LogOut, Shield } from 'lucide-react';
import { NHSLogo } from './NHSLogo';
import { NotificationDropdown } from './NotificationDropdown';

interface HeaderProps {
  userRole: 'gp' | 'specialist' | 'admin';
  userName?: string;
  onLogout?: () => void;
}

export function Header({ userRole, userName, onLogout }: HeaderProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const basePath = userRole === 'admin' ? '/admin' : userRole === 'gp' ? '/gp' : '/specialist';

  const isQueriesActive = location.pathname.includes('/queries') || location.pathname.includes('/query/');
  const isAdminActive = location.pathname.startsWith('/admin');

  const handleLogout = () => {
    onLogout?.();
    navigate('/login');
  };

  const roleLabel =
    userRole === 'gp' ? 'For GPs' : userRole === 'specialist' ? 'For Specialists' : 'Admin';

  return (
    <header className="bg-[var(--nhs-blue)] shadow-lg sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16 lg:h-20">
          <div className="flex items-center gap-3 sm:gap-4 min-w-0">
            <NHSLogo />
            <span className="text-white font-medium text-base sm:text-lg border-l border-white/30 pl-3 sm:pl-4 truncate">
              {roleLabel}
            </span>
          </div>

          <nav className="flex items-center gap-3 sm:gap-4 lg:gap-6">
            {userRole !== 'admin' && (
              <Link
                to={`${basePath}/queries`}
                className={`text-white font-medium hover:text-white/80 transition-colors px-3 py-2 rounded ${
                  isQueriesActive ? 'bg-[var(--nhs-dark-blue)]' : ''
                }`}
              >
                Queries
              </Link>
            )}

            {userRole === 'admin' && (
              <Link
                to="/admin/users"
                className={`text-white font-medium hover:text-white/80 transition-colors px-3 py-2 rounded ${
                  isAdminActive ? 'bg-[var(--nhs-dark-blue)]' : ''
                }`}
              >
                <span className="inline-flex items-center gap-1.5">
                  <Shield className="w-4 h-4" />
                  Admin Panel
                </span>
              </Link>
            )}

            <NotificationDropdown userRole={userRole} />

            <div className="flex items-center gap-2 text-white">
              <Link
                to="/profile"
                className="flex items-center gap-2 text-white hover:text-white/80 transition-colors rounded px-2 py-1"
                title="My Profile"
              >
                <div className="w-10 h-10 bg-white rounded-full flex items-center justify-center">
                  <User className="w-6 h-6 text-[var(--nhs-blue)]" />
                </div>
                {userName && (
                  <span className="hidden md:block text-sm font-medium">{userName}</span>
                )}
              </Link>
            </div>

            {onLogout && (
              <button
                onClick={handleLogout}
                className="text-white/80 hover:text-white transition-colors p-2 rounded hover:bg-white/10"
                title="Logout"
              >
                <LogOut className="w-5 h-5" />
              </button>
            )}
          </nav>
        </div>
      </div>
    </header>
  );
}
