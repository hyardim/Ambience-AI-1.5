import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, CheckCircle, LoaderCircle } from 'lucide-react';

import { AuthHeader } from '../../components/AuthHeader';
import { confirmEmailVerification } from '../../services/api';

export function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') ?? '';

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  useEffect(() => {
    if (!token) {
      setError('Verification token is missing. Request a new verification email.');
      return;
    }

    let mounted = true;
    setIsLoading(true);

    confirmEmailVerification(token)
      .then((response) => {
        if (mounted) {
          setSuccessMessage(response.message || 'Email verified successfully');
        }
      })
      .catch((err) => {
        if (!mounted) return;
        const fallback = 'Invalid or expired verification link. Request a new one.';
        setError(err instanceof Error ? err.message || fallback : fallback);
      })
      .finally(() => {
        if (mounted) {
          setIsLoading(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, [token]);

  return (
    <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
      <AuthHeader />

      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-md">
          <div className="bg-white rounded-2xl shadow-xl p-8 sm:p-10 text-center">
            <h1 className="text-2xl font-bold text-gray-900 mb-4">Verify your email</h1>

            {isLoading && (
              <div className="flex flex-col items-center gap-3 text-gray-700 py-4">
                <LoaderCircle className="w-8 h-8 animate-spin" />
                <p>Verifying your link…</p>
              </div>
            )}

            {!isLoading && successMessage && (
              <>
                <CheckCircle className="w-12 h-12 text-green-500 mx-auto mb-4" />
                <p className="text-gray-700 mb-6">{successMessage}</p>
                <Link
                  to="/login"
                  className="inline-flex items-center gap-2 text-[#005eb8] hover:text-[#003087] font-medium"
                >
                  <ArrowLeft className="w-4 h-4" />
                  Continue to Login
                </Link>
              </>
            )}

            {!isLoading && error && (
              <>
                <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm text-left">
                  {error}
                </div>
                <Link
                  to="/resend-verification"
                  className="inline-flex items-center gap-2 text-[#005eb8] hover:text-[#003087] font-medium"
                >
                  <ArrowLeft className="w-4 h-4" />
                  Resend verification email
                </Link>
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
