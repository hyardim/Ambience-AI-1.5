import { useState, useRef, useCallback, useEffect } from 'react';
import { subscribeToChatStream } from '../services/api';
import { nextTimeoutPhase, settleResolver } from '../utils/chatStream';
import { mapCitations } from '../utils/messageMapping';
import type { Message } from '../types';

// ── Stream lifecycle states ──────────────────────────────────────────────

export type StreamPhase =
  | 'idle'
  | 'connecting'
  | 'streaming'
  | 'completed'
  | 'fallback_polling';

export interface UseChatStreamOptions {
  /** Current chat ID (null when chat not yet loaded). */
  chatId: number | null;
  /** Callback to silently refresh chat data from the server. */
  onRefresh: () => Promise<void>;
  /** Polling interval in ms when in fallback_polling phase. Default: 2000. */
  pollInterval?: number;
  /** SSE connect timeout in ms. Default: 500. */
  connectTimeout?: number;
  /** Optional callback when backend reports truncated file context. */
  onFileContextTruncated?: () => void;
}

export interface UseChatStreamReturn {
  /** Current streaming lifecycle phase. */
  phase: StreamPhase;
  /** Whether an SSE connection is actively receiving events. */
  isStreaming: boolean;
  /** Whether polling fallback is active. */
  isPolling: boolean;
  /**
   * Open an SSE connection for the given chat.
   * Resolves once connected (or after timeout fallback).
   * Safe to call multiple times — previous connection is cleaned up first.
   */
  connectStream: (chatId: number) => Promise<void>;
  /** Disconnect any active SSE stream. */
  disconnectStream: () => void;
  /**
   * Apply a streaming event to the messages array.
   * This is called internally by the hook; the messages state updater
   * is provided so the page component retains ownership of messages state.
   */
  applyStreamEvent: null; // unused externally — events applied via setMessages
  /**
   * Start polling mode explicitly (e.g. when SSE is unavailable).
   */
  startPolling: () => void;
  /**
   * Stop polling mode.
   */
  stopPolling: () => void;
  /**
   * Pass the setMessages dispatcher so the hook can update messages on SSE events.
   */
  // The hook applies events directly; the page passes setMessages at init.
}

/**
 * Hook that manages the SSE streaming lifecycle for a chat detail page.
 *
 * State machine transitions:
 *   idle → connecting   (connectStream called)
 *   connecting → streaming   (stream_start received)
 *   connecting → fallback_polling   (connection error / timeout)
 *   streaming → completed   (complete event received)
 *   streaming → fallback_polling   (error event / connection drop)
 *   fallback_polling → idle   (refresh finds completed state)
 *   completed → idle   (reset after reconciliation)
 *   any → idle   (disconnectStream / unmount)
 */
export function useChatStream(
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>,
  options: UseChatStreamOptions,
) {
  const {
    chatId,
    onRefresh,
    pollInterval = 2000,
    connectTimeout = 500,
    onFileContextTruncated,
  } = options;

  const [phase, setPhase] = useState<StreamPhase>('idle');
  const cleanupRef = useRef<(() => void) | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Guard against calling setPhase after unmount
  const mountedRef = useRef(true);

  // ── Cleanup on unmount ────────────────────────────────────────────────
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      cleanupRef.current?.();
      cleanupRef.current = null;
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, []);

  // ── Cleanup on chatId change ──────────────────────────────────────────
  useEffect(() => {
    return () => {
      cleanupRef.current?.();
      cleanupRef.current = null;
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
        pollTimerRef.current = null;
      }
      if (mountedRef.current) setPhase('idle');
    };
  }, [chatId]);

  // ── Polling logic (exponential backoff) ──────────────────────────────
  const pollDelayRef = useRef(pollInterval);

  /**
   * Starts polling with exponential backoff.
   * Each successive poll increases the delay by 1.5x, capping at 30 seconds.
   */
  const startPolling = useCallback(() => {
    if (pollTimerRef.current) return; // already polling
    if (!mountedRef.current) return;
    setPhase('fallback_polling');
    pollDelayRef.current = pollInterval;
    const poll = () => {
      void onRefresh().then(() => {
        if (!mountedRef.current) return;
        pollDelayRef.current = Math.min(pollDelayRef.current * 1.5, 30000);
        pollTimerRef.current = setTimeout(poll, pollDelayRef.current);
      });
    };
    pollTimerRef.current = setTimeout(poll, pollDelayRef.current);
  }, [onRefresh, pollInterval]);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
    if (mountedRef.current) setPhase('idle');
  }, []);

  // ── Disconnect ────────────────────────────────────────────────────────
  const disconnectStream = useCallback(() => {
    cleanupRef.current?.();
    cleanupRef.current = null;
    stopPolling();
  }, [stopPolling]);

  // ── Connect ───────────────────────────────────────────────────────────
  const connectStream = useCallback(
    (targetChatId: number): Promise<void> => {
      // Tear down any previous connection (prevents duplicate subscriptions)
      cleanupRef.current?.();
      cleanupRef.current = null;

      if (!mountedRef.current) return Promise.resolve();

      setPhase('connecting');

      return new Promise<void>((resolve) => {
        let resolved = false;
        const settle = () => {
          resolved = settleResolver(resolved, resolve);
        };

        // Timeout fallback — don't block the caller forever
        const timer = setTimeout(() => {
          settle();
          // If still in connecting state, fall through to polling
          if (mountedRef.current) {
            setPhase((prev) => nextTimeoutPhase(prev));
            startPolling();
          }
        }, connectTimeout);

        const cleanup = subscribeToChatStream(targetChatId, {
          onOpen() {
            clearTimeout(timer);
            settle();
            // Stay in 'connecting' until stream_start arrives
          },

          onStreamStart(messageId) {
            if (!mountedRef.current) return;
            setPhase('streaming');
            // Stop polling if it was running (e.g. reconnect scenario)
            if (pollTimerRef.current) {
              clearTimeout(pollTimerRef.current);
              pollTimerRef.current = null;
            }
            // Insert placeholder AI message if not already present
            setMessages((prev) => {
              const existingGenerating = prev.find(
                (m) => m.isGenerating && m.senderType === 'ai',
              );
              if (existingGenerating) {
                return existingGenerating.id === String(messageId)
                  ? prev
                  : prev.map((m) =>
                      m.id === existingGenerating.id ? { ...m, id: String(messageId) } : m,
                    );
              }
              if (prev.find((m) => m.id === String(messageId))) return prev;
              const placeholder: Message = {
                id: String(messageId),
                senderId: 'ai',
                senderName: 'NHS AI Assistant',
                senderType: 'ai',
                content: '',
                timestamp: new Date(),
                isGenerating: true,
              };
              return [...prev, placeholder];
            });
          },

          onContent(messageId, content) {
            if (!mountedRef.current) return;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === String(messageId)
                  ? { ...m, content, isGenerating: true }
                  : m,
              ),
            );
          },

          onComplete(messageId, content, citations) {
            if (!mountedRef.current) return;
            setMessages((prev) =>
              prev.map((m) =>
                m.id === String(messageId)
                  ? {
                      ...m,
                      content,
                      citations: mapCitations(citations),
                      isGenerating: false,
                    }
                  : m,
              ),
            );
            setPhase('completed');
            cleanupRef.current = null;
            // Reconcile with persisted state
            void onRefresh().then(() => {
              if (mountedRef.current) setPhase('idle');
            });
          },

          onFileContextTruncated() {
            onFileContextTruncated?.();
          },

          onError() {
            if (!mountedRef.current) return;
            cleanupRef.current = null;
            // Fall back to polling
            setPhase('fallback_polling');
            startPolling();
          },

          onConnectionError() {
            if (!mountedRef.current) return;
            clearTimeout(timer);
            settle();
            cleanupRef.current = null;
            // SSE failed to connect — rely on polling fallback
            setPhase('fallback_polling');
            startPolling();
          },
        });

        cleanupRef.current = cleanup;
      });
    },
    [connectTimeout, onFileContextTruncated, onRefresh, setMessages, startPolling],
  );

  return {
    phase,
    isStreaming: phase === 'streaming' || phase === 'connecting',
    isPolling: phase === 'fallback_polling',
    connectStream,
    disconnectStream,
    startPolling,
    stopPolling,
    applyStreamEvent: null,
  };
}
