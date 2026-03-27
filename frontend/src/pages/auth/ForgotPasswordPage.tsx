import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, CheckCircle } from 'lucide-react';
import { AuthHeader } from '../../components/AuthHeader';
import { forgotPassword } from '../../services/api';

/** Forgot password page with email format validation. */
export function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [fieldError, setFieldError] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  /** Validates email format before requesting a password reset link. */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setFieldError('');

    if (!email) {
      setFieldError('Email is required');
      return;
    }

    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setFieldError('Please enter a valid email address');
      return;
    }

    setSubmitting(true);
    try {
      const response = await forgotPassword(email);
      setSuccessMessage(response.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
      <AuthHeader />

      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-md">
          <div className="bg-white rounded-2xl shadow-xl p-8 sm:p-10">
            <h1 className="text-2xl font-bold text-gray-900 text-center mb-2">
              Forgot your password?
            </h1>

            {successMessage ? (
              <div className="text-center mt-6">
                <CheckCircle className="w-12 h-12 text-green-500 mx-auto mb-4" />
                <p className="text-gray-700 mb-6">{successMessage}</p>
                <Link
                  to="/login"
                  className="inline-flex items-center gap-2 text-[#005eb8] hover:text-[#003087] font-medium"
                >
                  <ArrowLeft className="w-4 h-4" />
                  Back to Login
                </Link>
              </div>
            ) : (
              <>
                <p className="text-gray-600 text-center mb-8">
                  Enter your account email and we will send you a secure reset link.
                </p>

                {error && (
                  <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                    {error}
                  </div>
                )}

                <form onSubmit={handleSubmit} className="space-y-5">
                  <div>
                    <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
                      Email address
                    </label>
                    <input
                      id="email"
                      type="email"
                      value={email}
                      onChange={(e) => {
                        setEmail(e.target.value);
                        setFieldError('');
                      }}
                      className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent"
                      placeholder="you@example.com"
                      autoComplete="email"
                    />
                    {fieldError && <p className="text-sm text-red-600 mt-1">{fieldError}</p>}
                  </div>

                  <button
                    type="submit"
                    disabled={submitting}
                    className="w-full bg-[#005eb8] text-white py-3 px-4 rounded-lg font-medium hover:bg-[#003087] transition-colors focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:ring-offset-2 disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    {submitting ? 'Sending…' : 'Send Reset Link'}
                  </button>
                </form>

                <Link
                  to="/login"
                  className="flex items-center justify-center gap-2 text-[#005eb8] hover:text-[#003087] font-medium mt-6"
                >
                  <ArrowLeft className="w-4 h-4" />
                  Back to Login
                </Link>
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
