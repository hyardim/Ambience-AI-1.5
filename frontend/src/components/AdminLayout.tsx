import { NavLink } from 'react-router-dom';
import { Users, MessageSquare, ClipboardList } from 'lucide-react';
import { Header } from './Header';
import { useAuth } from '../contexts/AuthContext';

interface AdminLayoutProps {
  children: React.ReactNode;
}

const NAV_ITEMS = [
  { to: '/admin/users', label: 'Users', icon: Users },
  { to: '/admin/chats', label: 'Chats', icon: MessageSquare },
  { to: '/admin/logs', label: 'Audit Logs', icon: ClipboardList },
];

export function AdminLayout({ children }: AdminLayoutProps) {
  const { username, logout } = useAuth();

  return (
    <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
      <Header userRole="admin" userName={username || 'Admin'} onLogout={logout} />

      <div className="flex-1 flex">
        {/* Sidebar */}
        <aside className="w-56 bg-white border-r border-gray-200 shrink-0">
          <nav className="p-4 space-y-1">
            {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-[#005eb8] text-white'
                      : 'text-gray-700 hover:bg-gray-100'
                  }`
                }
              >
                <Icon className="w-5 h-5" />
                {label}
              </NavLink>
            ))}
          </nav>
        </aside>

        {/* Main content */}
        <main className="flex-1 p-6 lg:p-8 overflow-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
