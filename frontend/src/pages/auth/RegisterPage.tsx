import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Eye, EyeOff } from 'lucide-react';
import { AuthHeader } from '../../components/AuthHeader';
import { PasswordStrengthMeter } from '../../components/PasswordStrengthMeter';
import type { UserRole } from '../../types';
import { useAuth } from '../../contexts/useAuth';
import { getErrorMessage } from '../../utils/errors';

function routeForRole(role: UserRole): string {
  if (role === 'specialist') return '/specialist/queries';
  if (role === 'admin') return '/admin/users';
  return '/gp/queries';
}

function isStrongPassword(password: string): boolean {
  return (
    password.length >= 8 &&
    /[A-Z]/.test(password) &&
    /[a-z]/.test(password) &&
    /\d/.test(password) &&
    /[!@#$%^&*()_+\-=[\]{}|;:'",.<>?/`~\\]/.test(password)
  );
}

export function RegisterPage() {
  const [formData, setFormData] = useState({
    firstName: '',
    lastName: '',
    email: '',
    password: '',
    confirmPassword: '',
    role: 'gp' as UserRole,
    specialty: '',
  });
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [error, setError] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [successMessage, setSuccessMessage] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const navigate = useNavigate();
  const { register } = useAuth();

  /** Clears field-level error on change and updates form state. */
  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: value,
      specialty:
        name === 'role'
          ? value !== 'specialist'
            ? ''
            : prev.specialty
          : name === 'specialty'
            ? value
            : prev.specialty,
    }));
    setFieldErrors((prev) => ({ ...prev, [e.target.name]: '' }));
  };

  /**
   * Validates all registration fields and submits the form.
   * Sets per-field errors for missing or invalid values.
   */
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSuccessMessage('');

    const normalizedEmail = formData.email.trim().toLowerCase();
    const trimmedFirstName = formData.firstName.trim();
    const trimmedLastName = formData.lastName.trim();
    const errors: Record<string, string> = {};
    if (!trimmedFirstName) errors.firstName = 'First name is required';
    if (!trimmedLastName) errors.lastName = 'Last name is required';
    if (!normalizedEmail) {
      errors.email = 'Email is required';
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizedEmail)) {
      errors.email = 'Please enter a valid email address';
    }
    if (!formData.password) {
      errors.password = 'Password is required';
    } else if (!isStrongPassword(formData.password)) {
      errors.password =
        'Password must be at least 8 characters and include uppercase, lowercase, a number, and a special character.';
    }
    if (!formData.confirmPassword) {
      errors.confirmPassword = 'Please confirm your password';
    } else if (formData.password !== formData.confirmPassword) {
      errors.confirmPassword = 'Passwords do not match';
    }
    if (formData.role === 'specialist' && !formData.specialty) {
      errors.specialty = 'Specialty is required for specialists';
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setIsSubmitting(true);
    try {
      const result = await register({
        full_name: `${trimmedFirstName} ${trimmedLastName}`.trim(),
        email: normalizedEmail,
        password: formData.password,
        role: formData.role,
        specialty: formData.role === 'specialist' ? formData.specialty : undefined,
      });
      if (result.requiresEmailVerification) {
        setSuccessMessage(result.message);
      } else if (result.role) {
        navigate(routeForRole(result.role));
      }
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to create account'));
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[var(--nhs-page-bg)] flex flex-col">
      <AuthHeader />

      <main className="flex-1 flex items-center justify-center px-4 py-12">
        <div className="w-full max-w-md">
          <div className="bg-white rounded-2xl shadow-xl p-8 sm:p-10">
            <h1 className="text-2xl font-bold text-gray-900 text-center mb-8">
              Create your Account
            </h1>

            {successMessage && (
              <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded-lg text-green-800 text-sm">
                <p>{successMessage}</p>
                <p className="mt-2">
                  Check your inbox for the verification link before signing in.
                </p>
                <Link
                  to={`/resend-verification?email=${encodeURIComponent(formData.email)}`}
                  className="mt-3 inline-block text-[#005eb8] hover:text-[#003087] font-medium"
                >
                  Resend verification email
                </Link>
              </div>
            )}

            {error && (
              <div
                role="alert"
                aria-live="polite"
                className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm"
              >
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-5">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label
                    htmlFor="firstName"
                    className="block text-sm font-medium text-gray-700 mb-2"
                  >
                    First Name
                  </label>
                  <input
                    type="text"
                    id="firstName"
                    name="firstName"
                    value={formData.firstName}
                    onChange={handleChange}
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--nhs-blue)] focus:border-transparent"
                    placeholder="John"
                    required
                  />
                  {fieldErrors.firstName && (
                    <p className="text-sm text-red-600 mt-1">{fieldErrors.firstName}</p>
                  )}
                </div>
                <div>
                  <label
                    htmlFor="lastName"
                    className="block text-sm font-medium text-gray-700 mb-2"
                  >
                    Last Name
                  </label>
                  <input
                    type="text"
                    id="lastName"
                    name="lastName"
                    value={formData.lastName}
                    onChange={handleChange}
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--nhs-blue)] focus:border-transparent"
                    placeholder="Smith"
                    required
                  />
                  {fieldErrors.lastName && (
                    <p className="text-sm text-red-600 mt-1">{fieldErrors.lastName}</p>
                  )}
                </div>
              </div>

              <div>
                <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-2">
                  Email Address
                </label>
                <input
                  type="email"
                  id="email"
                  name="email"
                  value={formData.email}
                  onChange={handleChange}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--nhs-blue)] focus:border-transparent"
                  placeholder="john.smith@nhs.uk"
                  required
                />
                {fieldErrors.email && (
                  <p className="text-sm text-red-600 mt-1">{fieldErrors.email}</p>
                )}
              </div>

              <div>
                <label htmlFor="role" className="block text-sm font-medium text-gray-700 mb-2">
                  Role
                </label>
                <select
                  id="role"
                  name="role"
                  value={formData.role}
                  onChange={handleChange}
                  className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--nhs-blue)] focus:border-transparent"
                  required
                >
                  <option value="gp">General Practitioner</option>
                  <option value="specialist">Specialist</option>
                  <option value="admin">Admin</option>
                </select>
              </div>

              {formData.role === 'specialist' && (
                <div>
                  <label
                    htmlFor="specialty"
                    className="block text-sm font-medium text-gray-700 mb-2"
                  >
                    Specialty <span className="text-red-500">*</span>
                  </label>
                  <select
                    id="specialty"
                    name="specialty"
                    value={formData.specialty}
                    onChange={handleChange}
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--nhs-blue)] focus:border-transparent"
                    required
                  >
                    <option value="">Select specialty...</option>
                    <option value="neurology">Neurology</option>
                    <option value="rheumatology">Rheumatology</option>
                  </select>
                  {fieldErrors.specialty && (
                    <p className="text-sm text-red-600 mt-1">{fieldErrors.specialty}</p>
                  )}
                </div>
              )}

              <div>
                <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-2">
                  Password
                </label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    id="password"
                    name="password"
                    value={formData.password}
                    onChange={handleChange}
                    className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--nhs-blue)] focus:border-transparent pr-12"
                    placeholder="Create a password"
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
                <PasswordStrengthMeter password={formData.password} />
                {fieldErrors.password && (
                  <p className="text-sm text-red-600 mt-1">{fieldErrors.password}</p>
                )}
              </div>

              <div>
                <label
                  htmlFor="confirmPassword"
                  className="block text-sm font-medium text-gray-700 mb-2"
                >
                  Confirm Password
                </label>
                <div className="relative">
                  <input
                    type={showConfirmPassword ? 'text' : 'password'}
                    id="confirmPassword"
                    name="confirmPassword"
                    value={formData.confirmPassword}
                    onChange={handleChange}
                    className="w-full px-4 py-3 pr-12 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--nhs-blue)] focus:border-transparent"
                    placeholder="Confirm your password"
                    required
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-700"
                    aria-label={
                      showConfirmPassword ? 'Hide confirm password' : 'Show confirm password'
                    }
                  >
                    {showConfirmPassword ? (
                      <EyeOff className="w-5 h-5" />
                    ) : (
                      <Eye className="w-5 h-5" />
                    )}
                  </button>
                </div>
                {fieldErrors.confirmPassword && (
                  <p className="text-sm text-red-600 mt-1">{fieldErrors.confirmPassword}</p>
                )}
              </div>

              <button
                type="submit"
                disabled={isSubmitting}
                className="w-full bg-[var(--nhs-blue)] text-white py-3 px-4 rounded-lg font-medium hover:bg-[var(--nhs-dark-blue)] transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--nhs-blue)] focus:ring-offset-2"
              >
                {isSubmitting ? 'Creating Account...' : 'Create Account'}
              </button>
            </form>

            <p className="mt-6 text-center text-gray-600">
              Already have an account?{' '}
              <Link
                to="/login"
                className="text-[var(--nhs-blue)] hover:text-[var(--nhs-dark-blue)] font-medium"
              >
                Login here
              </Link>
            </p>
          </div>
        </div>
      </main>
    </div>
  );
}
