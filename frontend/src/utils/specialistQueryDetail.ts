export function shouldAutoConnectSpecialistStream(params: {
  hasChat: boolean;
  streamConnected: boolean;
  streamPhase: string;
  hasPendingAIResponse: boolean;
  hasRevisionInProgress: boolean;
}) {
  if (!params.hasChat || params.streamConnected) return false;
  if (params.streamPhase !== 'idle' && params.streamPhase !== 'fallback_polling') return false;
  return params.hasPendingAIResponse || params.hasRevisionInProgress;
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
