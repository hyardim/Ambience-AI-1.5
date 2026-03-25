import { useNavigate } from 'react-router-dom';

/**
 * Catch-all 404 page displayed when no other route matches.
 * Provides a link back to the home page.
 */
export function NotFoundPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-[var(--nhs-page-bg)] flex items-center justify-center">
      <div className="text-center max-w-md px-6">
        <h1 className="text-6xl font-bold text-gray-300 mb-4">404</h1>
        <h2 className="text-xl font-semibold text-gray-900 mb-2">Page not found</h2>
        <p className="text-gray-600 mb-6">
          The page you are looking for does not exist or has been moved.
        </p>
        <button
          onClick={() => navigate('/')}
          className="inline-flex items-center gap-2 bg-[var(--nhs-blue)] text-white px-6 py-3 rounded-lg font-medium hover:bg-[var(--nhs-dark-blue)] transition-colors"
        >
          Go to Home
        </button>
      </div>
    </div>
  );
}
