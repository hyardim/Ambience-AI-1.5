import { shouldAutoConnectStream } from './streamConnect';

export function shouldAutoConnectGpStream(params: {
  hasChat: boolean;
  streamConnected: boolean;
  sending: boolean;
  streamPhase: string;
  hasPendingAIResponse: boolean;
  hasRevisionInProgress: boolean;
}) {
  if (params.sending) return false;
  return shouldAutoConnectStream(params);
}
