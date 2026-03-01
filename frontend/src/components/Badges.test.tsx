import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StatusBadge, SeverityBadge } from './Badges';

describe('StatusBadge', () => {
  const statuses = [
    { value: 'active', label: 'Active' },
    { value: 'open', label: 'Open' },
    { value: 'submitted', label: 'Submitted' },
    { value: 'assigned', label: 'Assigned' },
    { value: 'reviewing', label: 'Reviewing' },
    { value: 'approved', label: 'Approved' },
    { value: 'resolved', label: 'Resolved' },
    { value: 'rejected', label: 'Rejected' },
    { value: 'closed', label: 'Closed' },
    { value: 'flagged', label: 'Flagged' },
    { value: 'pending-review', label: 'Pending Review' },
  ];

  statuses.forEach(({ value, label }) => {
    it(`renders "${label}" for status "${value}"`, () => {
      render(<StatusBadge status={value} />);
      expect(screen.getByText(label)).toBeInTheDocument();
    });
  });

  it('falls back to raw status for unknown values', () => {
    render(<StatusBadge status="custom-status" />);
    expect(screen.getByText('custom-status')).toBeInTheDocument();
  });
});

describe('SeverityBadge', () => {
  const severities = [
    { value: 'low', label: 'Low' },
    { value: 'medium', label: 'Medium' },
    { value: 'high', label: 'High' },
    { value: 'urgent', label: 'Urgent' },
    { value: 'routine', label: 'Routine' },
    { value: 'emergency', label: 'Emergency' },
  ];

  severities.forEach(({ value, label }) => {
    it(`renders "${label}" for severity "${value}"`, () => {
      render(<SeverityBadge severity={value} />);
      expect(screen.getByText(label)).toBeInTheDocument();
    });
  });

  it('falls back to raw severity for unknown values', () => {
    render(<SeverityBadge severity="custom-severity" />);
    expect(screen.getByText('custom-severity')).toBeInTheDocument();
  });
});
