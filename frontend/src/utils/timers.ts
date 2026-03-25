export function resetTimeout(
  ref: { current: ReturnType<typeof setTimeout> | null },
  callback: () => void,
  delayMs: number,
): void {
  if (ref.current) {
    clearTimeout(ref.current);
  }

  ref.current = setTimeout(callback, delayMs);
}

export function resetTimeoutWithValue<T>(
  ref: { current: ReturnType<typeof setTimeout> | null },
  callback: (value: T) => void,
  value: T,
  delayMs: number,
): void {
  resetTimeout(ref, () => callback(value), delayMs);
}
