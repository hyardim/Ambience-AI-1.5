import { describe, expect, it } from 'vitest';
import { mergeStreamingMessage, shouldAutoConnectGpStream } from '@/utils/gpDetail';
import type { Message } from '@/types';

const baseMessage: Message = {
  id: '1',
  senderId: 'user-1',
  senderName: 'Dr GP',
  senderType: 'gp',
  content: 'Hello',
  timestamp: new Date('2025-01-15T10:00:00Z'),
};

describe('gpDetail utilities', () => {
  it('does not auto-connect while a gp send is already in progress', () => {
    expect(
      shouldAutoConnectGpStream({
        hasChat: true,
        streamConnected: false,
        sending: true,
        streamPhase: 'idle',
        hasPendingAIResponse: true,
        hasRevisionInProgress: false,
      }),
    ).toBe(false);
  });

  it('returns fetched messages when there is no streaming placeholder', () => {
    const fetched = [{ ...baseMessage, id: '2', senderType: 'ai' as const }];

    expect(mergeStreamingMessage([baseMessage], fetched)).toEqual(fetched);
  });

  it('preserves the active streaming ai placeholder when ids match', () => {
    const streamingPlaceholder: Message = {
      ...baseMessage,
      id: 'ai-temp',
      senderType: 'ai',
      senderName: 'NHS AI Assistant',
      content: '',
      isGenerating: true,
    };
    const fetched: Message[] = [
      {
        ...streamingPlaceholder,
        content: 'Persisted content',
        isGenerating: false,
      },
    ];

    expect(mergeStreamingMessage([baseMessage, streamingPlaceholder], fetched)).toEqual([
      streamingPlaceholder,
    ]);
  });
});
