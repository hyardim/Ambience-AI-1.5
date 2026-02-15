import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Eye, EyeOff } from 'lucide-react';
import { AuthHeader } from '../../components/AuthHeader';
import { useAuth } from '../../contexts/AuthContext';

export function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const navigate = useNavigate();
  const { login, isAuthenticated } = useAuth();

  // If already authenticated, redirect to GP portal
  if (isAuthenticated) {
    navigate('/gp/queries', { replace: true });
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    
    if (!email || !password) {
      setError('Please enter your email/username and password');
      return;
    }

    setIsSubmitting(true);
    try {
      await login(email, password);
      navigate('/gp/queries');
    } catch {
      setError('Incorrect username or password');
    } finally {
      setIsSubmitting(false);
    }
  };

  const fillDemoCredentials = () => {
    setEmail('gp_user');
    setPassword('password123');
  };

  return (
    <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
      <AuthHeader />
      
      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-md">
          <div className="bg-white rounded-2xl shadow-xl p-8 sm:p-10">
            <h1 className="text-2xl font-bold text-gray-900 text-center mb-8">
              Login to your Account
            </h1>

            {/* Demo credentials hint */}
            <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <p className="text-sm text-blue-800 font-medium mb-1">Demo Credentials</p>
              <p className="text-sm text-blue-700">
                Username: <code className="bg-blue-100 px-1 rounded">gp_user</code> &nbsp;
                Password: <code className="bg-blue-100 px-1 rounded">password123</code>
              </p>
              <button
                type="button"
                onClick={fillDemoCredentials}
                className="mt-2 text-xs text-[#005eb8] hover:text-[#003087] font-medium underline"
              >
                Fill demo credentials
              </button>
            </div>

            {error && (
              <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-6">
              <div>
                <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-2">
                  Username / Email
                </label>
                <input
                  type="text"
                  id="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent"
                  placeholder="Enter your username or email"
                />
              </div>

              <div>
                <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-2">
                  Password
                </label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    id="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent pr-12"
                    placeholder="Enter your password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-700"
                  >
                    {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
              </div>

              <div className="text-right">
                <Link
                  to="/reset-password"
                  className="text-sm text-[#005eb8] hover:text-[#003087] font-medium"
                >
                  Forgot your password?
                </Link>
              </div>

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full bg-[#005eb8] text-white py-3 px-4 rounded-lg font-medium hover:bg-[#003087] transition-colors focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:ring-offset-2 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {isSubmitting ? 'Logging in...' : 'Login'}
              </button>
            </form>

            <p className="mt-8 text-center text-gray-600">
              Don't have an account?{' '}
              <Link to="/register" className="text-[#005eb8] hover:text-[#003087] font-medium">
                Register here
              </Link>
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}