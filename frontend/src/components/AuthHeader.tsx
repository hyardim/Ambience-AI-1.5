import { Link } from 'react-router-dom';
import { NHSLogo } from './NHSLogo';

export function AuthHeader() {
  return (
    <header className="bg-[#005eb8] shadow-lg">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <NHSLogo />
          <nav className="flex items-center gap-4">
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
          </nav>
        </div>
      </div>
    </header>
  );
}