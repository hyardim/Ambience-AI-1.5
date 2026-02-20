import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { AuthHeader } from '../../components/AuthHeader';

export function ResetPasswordPage() {
  return (
    <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
      <AuthHeader />

      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-md">
          <div className="bg-white rounded-2xl shadow-xl p-8 sm:p-10">
            <h1 className="text-2xl font-bold text-gray-900 text-center mb-4">
              Reset your Password
            </h1>
            <p className="text-gray-600 text-center mb-8">
              Password reset is not enabled yet in this deployment. Please contact an administrator to regain access.
            </p>

            <Link
              to="/login"
              className="flex items-center justify-center gap-2 text-[#005eb8] hover:text-[#003087] font-medium mt-6"
            >
              <ArrowLeft className="w-4 h-4" />
              Back to Login
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
