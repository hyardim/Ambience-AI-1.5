export function shouldAutoConnectStream(params: {
  hasChat: boolean;
  streamConnected: boolean;
  streamPhase: string;
  hasPendingAIResponse: boolean;
  hasRevisionInProgress: boolean;
  allowFallbackPolling?: boolean;
}) {
  if (!params.hasChat || params.streamConnected) return false;
  const validPhases = params.allowFallbackPolling ? ['idle', 'fallback_polling'] : ['idle'];
  if (!validPhases.includes(params.streamPhase)) return false;
  return params.hasPendingAIResponse || params.hasRevisionInProgress;
}
