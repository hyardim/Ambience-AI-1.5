import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Eye, EyeOff } from 'lucide-react';
import { AuthHeader } from '../../components/AuthHeader';
import { useAuth } from '../../contexts/useAuth';
import type { UserRole } from '../../types';
import { getErrorMessage } from '../../utils/errors';

const DEMO_LOGIN = {
  email: 'gp@example.com',
  password: 'Password123',
} as const;

function routeForRole(role: UserRole | null): string {
  if (role === 'specialist') return '/specialist/queries';
  if (role === 'admin') return '/admin/users';
  return '/gp/queries';
}

/** Login page with field-level validation and contextual API error messages. */
export function LoginPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({});
  const [unverifiedEmail, setUnverifiedEmail] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const navigate = useNavigate();
  const { login, isAuthenticated, role } = useAuth();

  useEffect(() => {
    if (isAuthenticated) {
      navigate(routeForRole(role), { replace: true });
    }
  }, [isAuthenticated, navigate, role]);

  /**
   * Validates fields and submits login credentials.
   * Maps API status codes to user-friendly field-level error messages.
   */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setUnverifiedEmail('');

    const errors: { email?: string; password?: string } = {};
    if (!email) errors.email = 'Email is required';
    if (!password) errors.password = 'Password is required';
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setIsSubmitting(true);
    try {
      const loggedInRole = await login(email, password);
      navigate(routeForRole(loggedInRole));
    } catch (err) {
      const message = getErrorMessage(err, 'Incorrect username or password');
      // Map well-known status codes to user-friendly messages
      if (
        message.includes('401') ||
        message.toLowerCase().includes('incorrect') ||
        message.toLowerCase().includes('invalid')
      ) {
        setError('Invalid email or password');
      } else if (
        message.includes('403') ||
        message.toLowerCase().includes('deactivated') ||
        message.toLowerCase().includes('disabled')
      ) {
        setError('Account deactivated');
      } else if (message.includes('429') || message.toLowerCase().includes('too many')) {
        setError('Too many attempts, please wait');
      } else {
        setError(message);
      }
      if (message.toLowerCase().includes('verify your email')) {
        setUnverifiedEmail(email);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const fillDemoCredentials = () => {
    setEmail(DEMO_LOGIN.email);
    setPassword(DEMO_LOGIN.password);
  };

  return (
    <div className="min-h-screen bg-[var(--nhs-page-bg)] flex flex-col">
      <AuthHeader />

      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-md">
          <div className="bg-white rounded-2xl shadow-xl p-8 sm:p-10">
            <h1 className="text-2xl font-bold text-gray-900 text-center mb-8">
              Login to your Account
            </h1>

            <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
              <p className="text-sm text-blue-800 font-medium mb-1">Demo Credentials</p>
              <p className="text-sm text-blue-700">
                Username: <code className="bg-blue-100 px-1 rounded">{DEMO_LOGIN.email}</code>{' '}
                &nbsp; Password:{' '}
                <code className="bg-blue-100 px-1 rounded">{DEMO_LOGIN.password}</code>
              </p>
              <button
                type="button"
                onClick={fillDemoCredentials}
                className="mt-2 text-xs text-[var(--nhs-blue)] hover:text-[var(--nhs-dark-blue)] font-medium underline"
              >
                Fill demo credentials
              </button>
            </div>

            {error && (
              <div
                role="alert"
                aria-live="polite"
                className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm"
              >
                {error}
                {unverifiedEmail && (
                  <div className="mt-2">
                    <Link
                      to={`/resend-verification?email=${encodeURIComponent(unverifiedEmail)}`}
                      className="text-[var(--nhs-blue)] hover:text-[var(--nhs-dark-blue)] font-medium"
                    >
                      Resend verification email
                    </Link>
                  </div>
                )}
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
                  onChange={(e) => {
                    setEmail(e.target.value);
                    setFieldErrors((prev) => ({ ...prev, email: undefined }));
                  }}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--nhs-blue)] focus:border-transparent"
                  placeholder="Enter your username or email"
                  required
                />
                {fieldErrors.email && (
                  <p className="text-sm text-red-600 mt-1">{fieldErrors.email}</p>
                )}
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
                    onChange={(e) => {
                      setPassword(e.target.value);
                      setFieldErrors((prev) => ({ ...prev, password: undefined }));
                    }}
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--nhs-blue)] focus:border-transparent pr-12"
                    placeholder="Enter your password"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-700"
                  >
                    {showPassword ? <EyeOff className="w-5 h-5" /> : <Eye className="w-5 h-5" />}
                  </button>
                </div>
                {fieldErrors.password && (
                  <p className="text-sm text-red-600 mt-1">{fieldErrors.password}</p>
                )}
              </div>

              <div className="text-right">
                <Link
                  to="/forgot-password"
                  className="text-sm text-[var(--nhs-blue)] hover:text-[var(--nhs-dark-blue)] font-medium"
                >
                  Forgot your password?
                </Link>
              </div>

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full bg-[var(--nhs-blue)] text-white py-3 px-4 rounded-lg font-medium hover:bg-[var(--nhs-dark-blue)] transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--nhs-blue)] focus:ring-offset-2 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {isSubmitting ? 'Logging in...' : 'Login'}
              </button>
            </form>

            <p className="mt-8 text-center text-gray-600">
              Don't have an account?{' '}
              <Link
                to="/register"
                className="text-[var(--nhs-blue)] hover:text-[var(--nhs-dark-blue)] font-medium"
              >
                Register here
              </Link>
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
