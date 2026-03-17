import type { BackendChat } from '../types/api';

export function formatSpecialtyLabel(specialty: string | null) {
  return specialty ? specialty.charAt(0).toUpperCase() + specialty.slice(1) : '—';
}

export function filterSpecialistChats(
  chats: BackendChat[],
  searchTerm: string,
  statusFilter: string,
  severityFilter: string,
) {
  const normalizedSearch = searchTerm.toLowerCase();
  return chats.filter((chat) => {
    const matchesSearch =
      (chat.title || '').toLowerCase().includes(normalizedSearch) ||
      (chat.specialty || '').toLowerCase().includes(normalizedSearch);
    const matchesStatus = statusFilter === 'all' || chat.status === statusFilter;
    const matchesSeverity = severityFilter === 'all' || chat.severity === severityFilter;
    return matchesSearch && matchesStatus && matchesSeverity;
  });
}
