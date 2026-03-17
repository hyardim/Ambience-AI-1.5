export function shouldAutoConnectGpStream(params: {
  hasChat: boolean;
  streamConnected: boolean;
  sending: boolean;
  streamPhase: string;
  hasPendingAIResponse: boolean;
  hasRevisionInProgress: boolean;
}) {
  if (!params.hasChat || params.streamConnected || params.sending) return false;
  if (params.streamPhase !== 'idle') return false;
  return params.hasPendingAIResponse || params.hasRevisionInProgress;
}
