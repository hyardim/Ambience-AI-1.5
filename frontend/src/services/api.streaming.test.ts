import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { subscribeToChatStream } from './api';

// ---------------------------------------------------------------------------
// Minimal mock for EventSource (not available in jsdom by default)
// ---------------------------------------------------------------------------

type ESListener = (ev: MessageEvent) => void;

class MockEventSource {
  static instances: MockEventSource[] = [];

  url: string;
  readyState = 0; // CONNECTING
  listeners: Record<string, ESListener[]> = {};
  onerror: ((ev: Event) => void) | null = null;
  onopen: ((ev: Event) => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: ESListener) {
    (this.listeners[type] ??= []).push(listener);
  }

  close() {
    this.closed = true;
    this.readyState = 2; // CLOSED
  }

  // -- helpers for tests ---------------------------------------------------

  /** Simulate the server pushing an SSE event */
  _emit(type: string, data: Record<string, unknown>) {
    const ev = new MessageEvent(type, { data: JSON.stringify(data) });
    for (const l of this.listeners[type] ?? []) l(ev);
  }

  /** Simulate a connection error */
  _triggerError() {
    this.onerror?.(new Event('error'));
  }

  /** Simulate the EventSource connection opening */
  _triggerOpen() {
    this.readyState = 1; // OPEN
    this.onopen?.(new Event('open'));
  }
}

// Inject into global scope so `subscribeToChatStream` can use it
// eslint-disable-next-line @typescript-eslint/no-explicit-any
(globalThis as any).EventSource = MockEventSource;

describe('subscribeToChatStream', () => {
  beforeEach(() => {
    MockEventSource.instances = [];
    localStorage.setItem('access_token', 'test-jwt');
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('opens an EventSource with the correct URL and token', () => {
    subscribeToChatStream(42, {});
    expect(MockEventSource.instances).toHaveLength(1);
    expect(MockEventSource.instances[0].url).toContain('/chats/42/stream');
    expect(MockEventSource.instances[0].url).toContain('token=test-jwt');
  });

  it('calls onStreamStart when stream_start event arrives', () => {
    const onStreamStart = vi.fn();
    subscribeToChatStream(1, { onStreamStart });

    const es = MockEventSource.instances[0];
    es._emit('stream_start', { chat_id: 1, message_id: 99 });

    expect(onStreamStart).toHaveBeenCalledWith(99);
  });

  it('calls onContent when content event arrives', () => {
    const onContent = vi.fn();
    subscribeToChatStream(1, { onContent });

    const es = MockEventSource.instances[0];
    es._emit('content', { chat_id: 1, message_id: 99, content: 'partial text' });

    expect(onContent).toHaveBeenCalledWith(99, 'partial text');
  });

  it('calls onComplete and closes the source on complete event', () => {
    const onComplete = vi.fn();
    subscribeToChatStream(1, { onComplete });

    const es = MockEventSource.instances[0];
    es._emit('complete', {
      chat_id: 1,
      message_id: 99,
      content: 'full answer',
      citations: [{ title: 'ref' }],
    });

    expect(onComplete).toHaveBeenCalledWith(99, 'full answer', [{ title: 'ref' }]);
    expect(es.closed).toBe(true);
  });

  it('calls onError and closes the source on error event', () => {
    const onError = vi.fn();
    subscribeToChatStream(1, { onError });

    const es = MockEventSource.instances[0];
    es._emit('error', { chat_id: 1, message_id: 99, error: 'boom' });

    expect(onError).toHaveBeenCalledWith(99, 'boom');
    expect(es.closed).toBe(true);
  });

  it('calls onConnectionError on EventSource native error', () => {
    const onConnectionError = vi.fn();
    subscribeToChatStream(1, { onConnectionError });

    const es = MockEventSource.instances[0];
    es._triggerError();

    expect(onConnectionError).toHaveBeenCalled();
    expect(es.closed).toBe(true);
  });

  it('cleanup function closes the EventSource', () => {
    const cleanup = subscribeToChatStream(1, {});
    const es = MockEventSource.instances[0];
    expect(es.closed).toBe(false);
    cleanup();
    expect(es.closed).toBe(true);
  });

  it('returns noop and fires onConnectionError when no token', () => {
    localStorage.removeItem('access_token');
    const onConnectionError = vi.fn();
    const cleanup = subscribeToChatStream(1, { onConnectionError });
    expect(onConnectionError).toHaveBeenCalled();
    expect(MockEventSource.instances).toHaveLength(0);
    // cleanup should be safe to call even though nothing was opened
    cleanup();
  });

  it('fires events in correct order: start → content → complete', () => {
    const order: string[] = [];
    subscribeToChatStream(1, {
      onStreamStart: () => order.push('start'),
      onContent: () => order.push('content'),
      onComplete: () => order.push('complete'),
    });

    const es = MockEventSource.instances[0];
    es._emit('stream_start', { chat_id: 1, message_id: 1 });
    es._emit('content', { chat_id: 1, message_id: 1, content: 'abc' });
    es._emit('complete', { chat_id: 1, message_id: 1, content: 'abc', citations: null });

    expect(order).toEqual(['start', 'content', 'complete']);
  });

  it('calls onOpen when the EventSource connection opens', () => {
    const onOpen = vi.fn();
    subscribeToChatStream(1, { onOpen });

    const es = MockEventSource.instances[0];
    expect(onOpen).not.toHaveBeenCalled();
    es._triggerOpen();
    expect(onOpen).toHaveBeenCalledOnce();
  });

  it('works without onOpen callback provided', () => {
    subscribeToChatStream(1, {});
    const es = MockEventSource.instances[0];
    // Should not throw when onopen fires without a callback
    expect(() => es._triggerOpen()).not.toThrow();
  });

  it('delivers multiple cumulative content events in order', () => {
    const contents: string[] = [];
    subscribeToChatStream(1, {
      onContent: (_id: number, content: string) => contents.push(content),
    });

    const es = MockEventSource.instances[0];
    es._emit('stream_start', { chat_id: 1, message_id: 1 });
    es._emit('content', { chat_id: 1, message_id: 1, content: 'H' });
    es._emit('content', { chat_id: 1, message_id: 1, content: 'He' });
    es._emit('content', { chat_id: 1, message_id: 1, content: 'Hel' });
    es._emit('content', { chat_id: 1, message_id: 1, content: 'Hell' });
    es._emit('content', { chat_id: 1, message_id: 1, content: 'Hello' });

    expect(contents).toEqual(['H', 'He', 'Hel', 'Hell', 'Hello']);
  });

  it('handles rapid start → content → error sequence without throwing', () => {
    const onError = vi.fn();
    const onContent = vi.fn();
    subscribeToChatStream(1, { onContent, onError });

    const es = MockEventSource.instances[0];
    es._emit('stream_start', { chat_id: 1, message_id: 1 });
    es._emit('content', { chat_id: 1, message_id: 1, content: 'partial' });
    es._emit('error', { chat_id: 1, message_id: 1, error: 'LLM timeout' });

    expect(onContent).toHaveBeenCalledWith(1, 'partial');
    expect(onError).toHaveBeenCalledWith(1, 'LLM timeout');
    expect(es.closed).toBe(true);
  });
});
