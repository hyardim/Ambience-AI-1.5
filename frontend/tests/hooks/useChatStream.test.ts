import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useChatStream } from '@/hooks/useChatStream';
import type { Message } from '@/types';

type StreamCallbacks = {
  onOpen?: () => void;
  onStreamStart?: (messageId: number) => void;
  onContent?: (messageId: number, content: string) => void;
  onComplete?: (messageId: number, content: string, citations: unknown[] | null) => void;
  onFileContextTruncated?: () => void;
  onError?: (messageId: number, errorMessage: string) => void;
  onConnectionError?: () => void;
};

// ---------------------------------------------------------------------------
// Mock subscribeToChatStream from the api module
// ---------------------------------------------------------------------------

const mockCleanup = vi.fn();

vi.mock('@/services/api', () => ({
  subscribeToChatStream: vi.fn((_chatId: number, callbacks: StreamCallbacks) => {
    // Store callbacks so tests can trigger them
    latestCallbacks = callbacks;
    return mockCleanup;
  }),
}));

let latestCallbacks: StreamCallbacks = {};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createWrapper() {
  let messages: Message[] = [];
  const setMessages: React.Dispatch<React.SetStateAction<Message[]>> = (action) => {
    messages = typeof action === 'function' ? action(messages) : action;
  };
  return { setMessages, getMessages: () => messages };
}

function createWrapperWithMessages(initialMessages: Message[]) {
  let messages = [...initialMessages];
  const setMessages: React.Dispatch<React.SetStateAction<Message[]>> = (action) => {
    messages = typeof action === 'function' ? action(messages) : action;
  };
  return { setMessages, getMessages: () => messages };
}

describe('useChatStream', () => {
  const mockRefresh = vi.fn().mockResolvedValue(undefined);
  let wrapper: ReturnType<typeof createWrapper>;

  beforeEach(() => {
    vi.useFakeTimers();
    wrapper = createWrapper();
    mockCleanup.mockClear();
    mockRefresh.mockClear();
    latestCallbacks = {};
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // ── Phase lifecycle tests ──────────────────────────────────────────

  it('starts in idle phase', () => {
    const { result } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
      }),
    );

    expect(result.current.phase).toBe('idle');
    expect(result.current.isStreaming).toBe(false);
    expect(result.current.isPolling).toBe(false);
  });

  it('transitions to connecting phase when connectStream is called', async () => {
    const { result } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
      }),
    );

    // Don't await — we want to inspect mid-connection state
    act(() => {
      result.current.connectStream(1);
    });

    expect(result.current.phase).toBe('connecting');
    expect(result.current.isStreaming).toBe(true);
  });

  it('transitions connecting → streaming on stream_start', async () => {
    const { result } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
      }),
    );

    act(() => {
      void result.current.connectStream(1);
    });

    // Simulate connection opening
    act(() => {
      latestCallbacks.onOpen?.();
    });

    // Simulate stream start
    act(() => {
      latestCallbacks.onStreamStart?.(42);
    });

    expect(result.current.phase).toBe('streaming');
    expect(result.current.isStreaming).toBe(true);
  });

  it('transitions streaming → completed on complete event', async () => {
    const { result } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
      }),
    );

    act(() => {
      result.current.connectStream(1);
    });
    act(() => {
      latestCallbacks.onOpen?.();
      latestCallbacks.onStreamStart?.(42);
    });

    expect(result.current.phase).toBe('streaming');

    await act(async () => {
      latestCallbacks.onComplete?.(42, 'Final answer', null);
      // Allow the onRefresh promise to resolve
      await Promise.resolve();
    });

    expect(result.current.phase).toBe('idle'); // completed → idle after refresh
    expect(mockRefresh).toHaveBeenCalled();
  });

  it('transitions connecting → fallback_polling on connection timeout', async () => {
    const { result } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
        connectTimeout: 200,
      }),
    );

    act(() => {
      result.current.connectStream(1);
    });

    expect(result.current.phase).toBe('connecting');

    // Advance past the timeout
    act(() => {
      vi.advanceTimersByTime(300);
    });

    expect(result.current.phase).toBe('fallback_polling');
    expect(result.current.isPolling).toBe(true);
  });

  it('transitions to fallback_polling on connection error', async () => {
    const { result } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
      }),
    );

    act(() => {
      result.current.connectStream(1);
    });

    act(() => {
      latestCallbacks.onConnectionError?.();
    });

    expect(result.current.phase).toBe('fallback_polling');
    expect(result.current.isPolling).toBe(true);
  });

  it('transitions streaming → fallback_polling on error event', async () => {
    const { result } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
      }),
    );

    act(() => {
      result.current.connectStream(1);
    });
    act(() => {
      latestCallbacks.onOpen?.();
      latestCallbacks.onStreamStart?.(42);
    });

    expect(result.current.phase).toBe('streaming');

    act(() => {
      latestCallbacks.onError?.(42, 'something went wrong');
    });

    expect(result.current.phase).toBe('fallback_polling');
    expect(result.current.isPolling).toBe(true);
  });

  // ── Duplicate connection prevention ────────────────────────────────

  it('cleans up previous stream when connectStream is called again', () => {
    const { result } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
      }),
    );

    act(() => {
      result.current.connectStream(1);
    });

    const firstCleanup = mockCleanup.mock.calls.length;

    act(() => {
      result.current.connectStream(1);
    });

    // The first stream's cleanup should have been called
    expect(mockCleanup).toHaveBeenCalledTimes(firstCleanup + 1);
  });

  // ── Message handling ──────────────────────────────────────────────

  it('inserts placeholder AI message on stream_start', () => {
    const { result } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
      }),
    );

    act(() => {
      result.current.connectStream(1);
    });
    act(() => {
      latestCallbacks.onStreamStart?.(42);
    });

    const messages = wrapper.getMessages();
    expect(messages).toHaveLength(1);
    expect(messages[0].id).toBe('42');
    expect(messages[0].senderType).toBe('ai');
    expect(messages[0].isGenerating).toBe(true);
    expect(messages[0].content).toBe('');
  });

  it('does not duplicate placeholder on repeated stream_start', () => {
    const { result } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
      }),
    );

    act(() => {
      result.current.connectStream(1);
    });
    act(() => {
      latestCallbacks.onStreamStart?.(42);
      latestCallbacks.onStreamStart?.(42);
    });

    expect(wrapper.getMessages()).toHaveLength(1);
  });

  it('updates message content on content event', () => {
    const { result } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
      }),
    );

    act(() => {
      result.current.connectStream(1);
    });
    act(() => {
      latestCallbacks.onStreamStart?.(42);
    });
    act(() => {
      latestCallbacks.onContent?.(42, 'Hello world');
    });

    const messages = wrapper.getMessages();
    expect(messages[0].content).toBe('Hello world');
    expect(messages[0].isGenerating).toBe(true);
  });

  it('finalizes message on complete event', async () => {
    const { result } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
      }),
    );

    act(() => {
      result.current.connectStream(1);
    });
    act(() => {
      latestCallbacks.onStreamStart?.(42);
    });

    await act(async () => {
      latestCallbacks.onComplete?.(42, 'Complete answer', [{ title: 'ref1' }]);
      await Promise.resolve();
    });

    const messages = wrapper.getMessages();
    expect(messages[0].content).toBe('Complete answer');
    expect(messages[0].isGenerating).toBe(false);
    expect(messages[0].citations).toHaveLength(1);
  });

  // ── Polling ────────────────────────────────────────────────────────

  it('polls with exponential backoff in fallback_polling phase', async () => {
    const { result } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
        pollInterval: 1000,
      }),
    );

    act(() => {
      result.current.startPolling();
    });

    expect(result.current.phase).toBe('fallback_polling');

    // First poll fires at 1000ms
    await act(async () => {
      vi.advanceTimersByTime(1000);
      await (vi.runAllTicsAsync ? vi.runAllTicsAsync() : Promise.resolve());
    });
    expect(mockRefresh).toHaveBeenCalledTimes(1);

    // Second poll fires at 1500ms (1000 * 1.5) after the first
    await act(async () => {
      vi.advanceTimersByTime(1500);
      await (vi.runAllTicsAsync ? vi.runAllTicsAsync() : Promise.resolve());
    });
    expect(mockRefresh).toHaveBeenCalledTimes(2);
  });

  it('stops polling when stopPolling is called', () => {
    const { result } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
        pollInterval: 1000,
      }),
    );

    act(() => {
      result.current.startPolling();
    });

    act(() => {
      vi.advanceTimersByTime(1500);
    });

    const callsBefore = mockRefresh.mock.calls.length;

    act(() => {
      result.current.stopPolling();
    });

    act(() => {
      vi.advanceTimersByTime(3000);
    });

    // No additional calls after stopPolling
    expect(mockRefresh).toHaveBeenCalledTimes(callsBefore);
    expect(result.current.phase).toBe('idle');
  });

  it('resets to idle when stopPolling is called without an active timer', () => {
    const { result } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
      }),
    );

    act(() => {
      result.current.stopPolling();
    });

    expect(result.current.phase).toBe('idle');
  });

  it('stops polling when stream connects successfully', () => {
    const { result } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
        pollInterval: 1000,
      }),
    );

    // Start in polling mode
    act(() => {
      result.current.startPolling();
    });

    // Connect stream
    act(() => {
      result.current.connectStream(1);
    });
    act(() => {
      latestCallbacks.onOpen?.();
      latestCallbacks.onStreamStart?.(42);
    });

    expect(result.current.phase).toBe('streaming');

    // Advance time — no more polls should happen
    mockRefresh.mockClear();
    act(() => {
      vi.advanceTimersByTime(5000);
    });

    expect(mockRefresh).not.toHaveBeenCalled();
  });

  it('cleans up polling and resets phase when chatId changes', () => {
    const { result, rerender } = renderHook(
      ({ chatId }) =>
        useChatStream(wrapper.setMessages, {
          chatId,
          onRefresh: mockRefresh,
          pollInterval: 1000,
        }),
      { initialProps: { chatId: 1 } },
    );

    act(() => {
      result.current.startPolling();
    });

    rerender({ chatId: 2 });

    act(() => {
      vi.advanceTimersByTime(3000);
    });

    expect(result.current.phase).toBe('idle');
    expect(mockRefresh).not.toHaveBeenCalled();
  });

  // ── Disconnect ─────────────────────────────────────────────────────

  it('disconnects and returns to idle', () => {
    const { result } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
      }),
    );

    act(() => {
      result.current.connectStream(1);
    });

    act(() => {
      result.current.disconnectStream();
    });

    expect(result.current.phase).toBe('idle');
    expect(mockCleanup).toHaveBeenCalled();
  });

  it('ignores duplicate polling starts and cleans up on unmount', () => {
    const { result, unmount } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
        pollInterval: 1000,
      }),
    );

    act(() => {
      result.current.startPolling();
      result.current.startPolling();
    });

    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(mockRefresh).toHaveBeenCalledTimes(1);

    unmount();

    act(() => {
      vi.advanceTimersByTime(2000);
    });

    expect(mockRefresh).toHaveBeenCalledTimes(1);
  });

  it('ignores content and completion events when no placeholder exists yet', async () => {
    const { result } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
      }),
    );

    act(() => {
      void result.current.connectStream(1);
      latestCallbacks.onOpen?.();
    });

    act(() => {
      latestCallbacks.onContent?.(42, 'ignored');
    });
    expect(wrapper.getMessages()).toEqual([]);

    await act(async () => {
      latestCallbacks.onComplete?.(42, 'still ignored', null);
      await Promise.resolve();
    });

    expect(wrapper.getMessages()).toEqual([]);
    expect(mockRefresh).toHaveBeenCalled();
  });

  it('keeps unrelated messages untouched while streaming updates a matching placeholder', async () => {
    const seeded = createWrapperWithMessages([
      {
        id: '7',
        senderId: 'user',
        senderName: 'GP User',
        senderType: 'gp',
        content: 'Existing message',
        timestamp: new Date(),
      },
    ]);

    const { result } = renderHook(() =>
      useChatStream(seeded.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
      }),
    );

    act(() => {
      void result.current.connectStream(1);
      latestCallbacks.onOpen?.();
      latestCallbacks.onStreamStart?.(42);
      latestCallbacks.onContent?.(42, 'Partial answer');
    });

    await act(async () => {
      latestCallbacks.onComplete?.(42, 'Final answer', []);
      await Promise.resolve();
    });

    expect(seeded.getMessages().find((message) => message.id === '7')?.content).toBe('Existing message');
    expect(seeded.getMessages().find((message) => message.id === '42')?.content).toBe('Final answer');
  });

  it('does not reset to idle after completion when refresh resolves after unmount', async () => {
    let resolveRefresh: (() => void) | null = null;
    const deferredRefresh = vi.fn(() => new Promise<void>((resolve) => {
      resolveRefresh = resolve;
    }));

    const { result, unmount } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: deferredRefresh,
      }),
    );

    act(() => {
      void result.current.connectStream(1);
      latestCallbacks.onOpen?.();
      latestCallbacks.onStreamStart?.(42);
    });

    act(() => {
      latestCallbacks.onComplete?.(42, 'Final answer', null);
    });

    unmount();

    await act(async () => {
      resolveRefresh?.();
      await Promise.resolve();
    });

    expect(deferredRefresh).toHaveBeenCalled();
  });

  it('no-ops when connectStream is called after unmount', async () => {
    const { result, unmount } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
      }),
    );

    unmount();

    await act(async () => {
      await result.current.connectStream(1);
    });

    expect(mockCleanup).not.toHaveBeenCalled();
  });

  it('ignores stream callbacks after unmount', async () => {
    const { result, unmount } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
      }),
    );

    act(() => {
      void result.current.connectStream(1);
    });

    unmount();

    act(() => {
      latestCallbacks.onStreamStart?.(42);
      latestCallbacks.onContent?.(42, 'ignored');
      latestCallbacks.onError?.(42, 'ignored');
      latestCallbacks.onConnectionError?.();
    });

    await act(async () => {
      latestCallbacks.onComplete?.(42, 'ignored', null);
      await Promise.resolve();
    });

    expect(wrapper.getMessages()).toEqual([]);
    expect(mockRefresh).not.toHaveBeenCalled();
  });

  it('does not start polling after unmount', () => {
    const { result, unmount } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
      }),
    );

    const startPolling = result.current.startPolling;
    unmount();

    act(() => {
      startPolling();
      vi.advanceTimersByTime(2000);
    });

    expect(mockRefresh).not.toHaveBeenCalled();
  });

  it('does not reset the phase when stopPolling is called after unmount', () => {
    const { result, unmount } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
      }),
    );

    act(() => {
      result.current.startPolling();
    });

    const stopPolling = result.current.stopPolling;
    unmount();

    act(() => {
      stopPolling();
    });

    expect(mockRefresh).not.toHaveBeenCalled();
  });

  it('keeps the current phase if timeout fires after streaming already started', () => {
    const { result } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
        connectTimeout: 100,
      }),
    );

    act(() => {
      void result.current.connectStream(1);
      latestCallbacks.onOpen?.();
      latestCallbacks.onStreamStart?.(42);
      vi.advanceTimersByTime(150);
    });

    expect(result.current.phase).toBe('streaming');
  });

  it('does not start fallback polling if the timeout fires after unmount', () => {
    const { result, unmount } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
        connectTimeout: 100,
      }),
    );

    act(() => {
      void result.current.connectStream(1);
    });

    unmount();

    act(() => {
      vi.advanceTimersByTime(150);
    });

    expect(mockRefresh).not.toHaveBeenCalled();
  });

  it('invokes onFileContextTruncated callback when the stream triggers it', () => {
    const onFileContextTruncated = vi.fn();
    const { result } = renderHook(() =>
      useChatStream(wrapper.setMessages, {
        chatId: 1,
        onRefresh: mockRefresh,
        onFileContextTruncated,
      }),
    );

    act(() => {
      void result.current.connectStream(1);
    });
    act(() => {
      latestCallbacks.onFileContextTruncated?.();
    });

    expect(onFileContextTruncated).toHaveBeenCalledOnce();
  });
});
