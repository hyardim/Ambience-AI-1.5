type TimeoutPhase = 'idle' | 'connecting' | 'streaming' | 'completed' | 'fallback_polling';

export function settleResolver(
  resolved: boolean,
  resolve: () => void,
) {
  if (!resolved) {
    resolve();
    return true;
  }
  return false;
}

export function nextTimeoutPhase(prev: TimeoutPhase): TimeoutPhase {
  return prev === 'connecting' ? 'fallback_polling' : prev;
}
