import type { ChatListFilters } from '../services/api';

export function fetchGpQueriesForSearch(
  fetchChats: (filters?: ChatListFilters) => Promise<void>,
  buildFilters: (searchOverride?: string) => ChatListFilters,
  nextValue: string,
) {
  return fetchChats(buildFilters(nextValue));
}

export function createGpQueriesSearchFetcher(
  fetchChats: (filters?: ChatListFilters) => Promise<void>,
  buildFilters: (searchOverride?: string) => ChatListFilters,
) {
  return (nextValue: string) => void fetchGpQueriesForSearch(fetchChats, buildFilters, nextValue);
}
