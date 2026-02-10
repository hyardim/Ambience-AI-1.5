import type { Severity, QueryStatus } from '../types';

interface StatusBadgeProps {
  status: QueryStatus;
}

export function StatusBadge({ status }: StatusBadgeProps) {
  const styles = {
    active: 'bg-blue-100 text-blue-800',
    resolved: 'bg-green-100 text-green-800',
    'pending-review': 'bg-yellow-100 text-yellow-800',
  };

  const labels = {
    active: 'Active',
    resolved: 'Resolved',
    'pending-review': 'Pending Review',
  };

  return (
    <span className={`px-3 py-1 rounded-full text-sm font-medium ${styles[status]}`}>
      {labels[status]}
    </span>
  );
}

interface SeverityBadgeProps {
  severity: Severity;
}

export function SeverityBadge({ severity }: SeverityBadgeProps) {
  const styles = {
    low: 'text-green-600',
    medium: 'text-yellow-600',
    high: 'text-red-600',
    urgent: 'text-red-800 font-bold',
  };

  const labels = {
    low: 'Low',
    medium: 'Medium',
    high: 'High',
    urgent: 'Urgent',
  };

  return (
    <span className={`font-medium ${styles[severity]}`}>
      {labels[severity]}
    </span>
  );
}
