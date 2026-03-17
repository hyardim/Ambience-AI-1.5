export function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

export function ifNotAbortError(error: unknown, callback: () => void): void {
  if (!isAbortError(error)) {
    callback();
  }
}
