import type { Severity, QueryStatus } from '../types';

// ---------------------------------------------------------------------------
// Status Badge — supports both legacy QueryStatus and backend ChatStatus strings
// ---------------------------------------------------------------------------

type ChatStatusString =
  | 'open' | 'submitted' | 'assigned' | 'reviewing'
  | 'approved' | 'rejected' | 'closed' | 'flagged';

interface StatusBadgeProps {
  status: QueryStatus | ChatStatusString | string;
}

const STATUS_STYLES: Record<string, string> = {
  active: 'bg-blue-100 text-blue-800',
  open: 'bg-blue-100 text-blue-800',
  submitted: 'bg-amber-100 text-amber-800',
  assigned: 'bg-purple-100 text-purple-800',
  reviewing: 'bg-indigo-100 text-indigo-800',
  approved: 'bg-green-100 text-green-800',
  resolved: 'bg-green-100 text-green-800',
  rejected: 'bg-red-100 text-red-800',
  closed: 'bg-gray-100 text-gray-800',
  flagged: 'bg-red-100 text-red-800',
  'pending-review': 'bg-yellow-100 text-yellow-800',
};

const STATUS_LABELS: Record<string, string> = {
  active: 'Active',
  open: 'Open',
  submitted: 'Submitted',
  assigned: 'Assigned',
  reviewing: 'Reviewing',
  approved: 'Approved',
  resolved: 'Resolved',
  rejected: 'Rejected',
  closed: 'Closed',
  flagged: 'Flagged',
  'pending-review': 'Pending Review',
};

export function StatusBadge({ status }: StatusBadgeProps) {
  const style = STATUS_STYLES[status] ?? 'bg-gray-100 text-gray-800';
  const label = STATUS_LABELS[status] ?? status;

  return (
    <span className={`px-3 py-1 rounded-full text-sm font-medium ${style}`}>
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Severity Badge
// ---------------------------------------------------------------------------

interface SeverityBadgeProps {
  severity: Severity | string;
}

const SEVERITY_STYLES: Record<string, string> = {
  low: 'text-green-600',
  medium: 'text-yellow-600',
  high: 'text-red-600',
  urgent: 'text-red-800 font-bold',
  routine: 'text-green-600',
  emergency: 'text-red-800 font-bold',
};

const SEVERITY_LABELS: Record<string, string> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  urgent: 'Urgent',
  routine: 'Routine',
  emergency: 'Emergency',
};

export function SeverityBadge({ severity }: SeverityBadgeProps) {
  const style = SEVERITY_STYLES[severity] ?? 'text-gray-600';
  const label = SEVERITY_LABELS[severity] ?? severity;

  return (
    <span className={`font-medium ${style}`}>
      {label}
    </span>
  );
}
