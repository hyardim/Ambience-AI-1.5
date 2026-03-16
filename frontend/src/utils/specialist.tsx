import { CheckCircle, XCircle } from 'lucide-react';

export function getCloseReviewTitle(
  anyGenerating: boolean,
  allAIReviewed: boolean,
): string | undefined {
  if (anyGenerating) {
    return 'Wait for AI response generation to finish';
  }

  if (!allAIReviewed) {
    return 'All AI responses must be reviewed before closing';
  }

  return undefined;
}

export function getTerminalConsultationState(status: string): {
  className: string;
  icon: typeof CheckCircle | typeof XCircle;
  label: string;
} {
  if (status === 'approved') {
    return {
      className: 'bg-green-50 text-green-700',
      icon: CheckCircle,
      label: 'Consultation Approved',
    };
  }

  return {
    className: 'bg-red-50 text-red-700',
    icon: XCircle,
    label: 'Consultation Rejected',
  };
}
