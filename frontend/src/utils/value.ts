export function orFallback<T extends string>(value: T | null | undefined, fallback: T): T {
  return value || fallback;
}

export function coalesce<T>(value: T | null | undefined, fallback: T): T {
  return value ?? fallback;
}
