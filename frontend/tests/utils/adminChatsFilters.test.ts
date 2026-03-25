import { describe, expect, it } from 'vitest';
import { filterAdminChats, replaceAdminChat } from '@/utils/adminChatsFilters';

const chats = [
  { id: 1, title: 'Headache', owner_identifier: 'gp-1' },
  { id: 2, title: 'Joint pain', owner_identifier: 'gp-2' },
] as const;

describe('adminChatsFilters', () => {
  it('replaces only the matching chat', () => {
    const updated = { id: 2, title: 'Updated', owner_identifier: 'gp-2' };
    expect(replaceAdminChat([...chats], 2, updated as never)).toEqual([
      chats[0],
      updated,
    ]);
  });

  it('filters by title or owner identifier', () => {
    expect(filterAdminChats([...chats] as never, 'head')).toHaveLength(1);
    expect(filterAdminChats([...chats] as never, 'gp-2')).toHaveLength(1);
    expect(filterAdminChats([...chats] as never, 'missing')).toHaveLength(0);
    expect(filterAdminChats([
      { id: 3, title: '', owner_identifier: 'owner-3' },
    ] as never, 'owner-3')).toHaveLength(1);
    expect(filterAdminChats([
      { id: 4, title: '', owner_identifier: null },
    ] as never, 'missing')).toHaveLength(0);
  });
});
