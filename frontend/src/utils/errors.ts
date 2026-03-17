export function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

export function isAbortError(error: unknown): boolean {
  /* v8 ignore next */
  return error instanceof DOMException && error.name === 'AbortError';
}
