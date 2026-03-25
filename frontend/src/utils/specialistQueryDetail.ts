import { shouldAutoConnectStream } from './streamConnect';

export function shouldAutoConnectSpecialistStream(params: {
  hasChat: boolean;
  streamConnected: boolean;
  streamPhase: string;
  hasPendingAIResponse: boolean;
  hasRevisionInProgress: boolean;
}) {
  return shouldAutoConnectStream({
    ...params,
    allowFallbackPolling: true,
  });
}

export function canAssignSpecialist(myUserId: number | null) {
  return myUserId !== null;
}

export function canSubmitReviewAction(input: string, reviewTargetMessageId: number | null) {
  return reviewTargetMessageId !== null && input.trim().length > 0;
}

export function canSubmitManualResponse(manualResponseContent: string, reviewTargetMessageId: number | null) {
  return reviewTargetMessageId !== null && manualResponseContent.trim().length > 0;
}
