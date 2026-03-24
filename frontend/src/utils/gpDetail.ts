import { shouldAutoConnectStream } from './streamConnect';
import type { Message } from '../types';

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

export function mergeStreamingMessage(
  previousMessages: Message[],
  fetchedMessages: Message[],
): Message[] {
  const streamingMessage = previousMessages.find(
    (message) => message.isGenerating && message.senderType === 'ai',
  );

  if (!streamingMessage) {
    return fetchedMessages;
  }

  return fetchedMessages.map((message) =>
    message.id === streamingMessage.id ? streamingMessage : message,
  );
}
