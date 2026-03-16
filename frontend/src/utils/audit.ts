export function formatAuditUserIdentifier(
  userIdentifier: string | null,
  userId: number | null,
): string {
  if (userIdentifier) {
    return userIdentifier;
  }

  if (userId) {
    return `#${userId}`;
  }

  return '—';
}
