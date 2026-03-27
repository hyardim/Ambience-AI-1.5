interface PatientContextBannerProps {
  age?: number | null;
  sex?: string | null;
  specialty?: string | null;
  urgency?: string | null;
  notes?: string | null;
  className?: string;
}

function toTitleCase(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function PatientContextBanner({
  age,
  sex,
  specialty,
  urgency,
  notes,
  className = '',
}: PatientContextBannerProps) {
  const chips: Array<{ label: string; value: string }> = [];
  if (age !== null && age !== undefined) {
    chips.push({ label: 'Age', value: String(age) });
  }
  if (sex) {
    chips.push({ label: 'Sex', value: toTitleCase(sex) });
  }
  if (specialty) {
    chips.push({ label: 'Specialty', value: toTitleCase(specialty) });
  }
  if (urgency) {
    chips.push({ label: 'Urgency', value: toTitleCase(urgency) });
  }

  const hasNotes = Boolean(notes && notes.trim());
  if (chips.length === 0 && !hasNotes) {
    return null;
  }

  return (
    <section className={`rounded-xl border border-sky-200 bg-sky-50 p-4 ${className}`.trim()}>
      <p className="text-xs font-semibold uppercase tracking-wide text-sky-800 mb-2">
        Patient Context
      </p>
      {chips.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2">
          {chips.map((chip) => (
            <span
              key={`${chip.label}-${chip.value}`}
              className="inline-flex items-center gap-1 rounded-full border border-sky-200 bg-white px-3 py-1 text-xs text-sky-900"
            >
              <span className="font-semibold">{chip.label}:</span>
              <span>{chip.value}</span>
            </span>
          ))}
        </div>
      )}
      {hasNotes && (
        <p className="text-sm text-sky-900 whitespace-pre-wrap break-words">
          <span className="font-semibold">Notes:</span> {notes}
        </p>
      )}
    </section>
  );
}
