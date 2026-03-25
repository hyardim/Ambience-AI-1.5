import { describe, expect, it } from 'vitest';
import { CheckCircle, XCircle } from 'lucide-react';
import { getCloseReviewTitle, getTerminalConsultationState } from '@/utils/specialist';

describe('specialist utils', () => {
  it('builds close-review button titles', () => {
    expect(getCloseReviewTitle(true, false)).toBe('Wait for AI response generation to finish');
    expect(getCloseReviewTitle(false, false)).toBe('All AI responses must be reviewed before closing');
    expect(getCloseReviewTitle(false, true)).toBeUndefined();
  });

  it('maps terminal consultation states', () => {
    expect(getTerminalConsultationState('approved')).toEqual({
      className: 'bg-green-50 text-green-700',
      icon: CheckCircle,
      label: 'Consultation Approved',
    });

    expect(getTerminalConsultationState('rejected')).toEqual({
      className: 'bg-red-50 text-red-700',
      icon: XCircle,
      label: 'Consultation Rejected',
    });
  });
});
