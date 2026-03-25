const RULES = [
  { label: '8+ characters',     test: (p: string) => p.length >= 8 },
  { label: 'Uppercase letter',  test: (p: string) => /[A-Z]/.test(p) },
  { label: 'Lowercase letter',  test: (p: string) => /[a-z]/.test(p) },
  { label: 'Number',            test: (p: string) => /\d/.test(p) },
  { label: 'Special character', test: (p: string) => /[^A-Za-z0-9]/.test(p) },
];

const BAR_COLOURS = ['bg-gray-200', 'bg-red-500', 'bg-red-500', 'bg-amber-400', 'bg-yellow-400', 'bg-green-500'];

const STRENGTH_LABELS = ['none', 'weak', 'weak', 'fair', 'good', 'strong'];

interface Props {
  password: string;
}

/** Visual password strength meter with ARIA progressbar attributes. */
export function PasswordStrengthMeter({ password }: Props) {
  if (!password.length) return null;

  const passed = RULES.filter(r => r.test(password)).length;
  const barColour = BAR_COLOURS[passed];
  const strengthLabel = STRENGTH_LABELS[passed];

  return (
    <div className="mt-2 space-y-2">
      {/* Strength bar */}
      <div
        className="flex gap-1"
        role="progressbar"
        aria-valuenow={passed}
        aria-valuemax={5}
        aria-label={`Password strength: ${strengthLabel}`}
      >
        {RULES.map((_, i) => (
          <div
            key={i}
            className={`h-1.5 flex-1 rounded-full transition-colors duration-200 ${
              i < passed ? barColour : 'bg-gray-200'
            }`}
          />
        ))}
      </div>

      {/* Rule checklist */}
      <ul className="grid grid-cols-2 gap-x-4 gap-y-0.5">
        {RULES.map(rule => {
          const ok = rule.test(password);
          return (
            <li key={rule.label} className={`flex items-center gap-1.5 text-xs ${ok ? 'text-green-600' : 'text-gray-400'}`}>
              <span>{ok ? '✓' : '–'}</span>
              {rule.label}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
