import type { AdminChatResponse } from '../types/api';

export function replaceAdminChat(
  chats: AdminChatResponse[],
  chatId: number,
  updated: AdminChatResponse,
) {
  return chats.map((chat) => (chat.id === chatId ? updated : chat));
}

export function filterAdminChats(chats: AdminChatResponse[], searchTerm: string) {
  const normalizedSearch = searchTerm.toLowerCase();
  return chats.filter((chat) =>
    (chat.title || '').toLowerCase().includes(normalizedSearch) ||
    (chat.owner_identifier || '').toLowerCase().includes(normalizedSearch),
  );
}
