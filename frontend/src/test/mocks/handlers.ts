import { http, HttpResponse } from 'msw';
import type { LoginResponse, UserProfile, BackendChat, BackendChatWithMessages, GPMessageResponse, NotificationResponse, AdminChatResponse, AuditLogResponse } from '../../types/api';

// ── Fixture data ──────────────────────────────────────────────────────────

export const mockGPUser: UserProfile = {
  id: 1,
  email: 'gp@example.com',
  full_name: 'Dr GP',
  role: 'gp',
  specialty: null,
  is_active: true,
};

export const mockSpecialistUser: UserProfile = {
  id: 2,
  email: 'specialist@example.com',
  full_name: 'Dr Specialist',
  role: 'specialist',
  specialty: 'neurology',
  is_active: true,
};

export const mockAdminUser: UserProfile = {
  id: 3,
  email: 'admin@example.com',
  full_name: 'Admin User',
  role: 'admin',
  specialty: null,
  is_active: true,
};

export const mockLoginResponse: LoginResponse = {
  access_token: 'mock-jwt-token',
  token_type: 'bearer',
  user: mockGPUser,
};

export const mockChat: BackendChat = {
  id: 1,
  title: 'Headache consultation',
  status: 'open',
  specialty: 'neurology',
  severity: 'medium',
  specialist_id: null,
  assigned_at: null,
  reviewed_at: null,
  review_feedback: null,
  created_at: '2025-01-15T10:00:00Z',
  user_id: 1,
};

export const mockChat2: BackendChat = {
  id: 2,
  title: 'Joint pain assessment',
  status: 'submitted',
  specialty: 'rheumatology',
  severity: 'high',
  specialist_id: null,
  assigned_at: null,
  reviewed_at: null,
  review_feedback: null,
  created_at: '2025-01-16T14:30:00Z',
  user_id: 1,
};

export const mockChatWithMessages: BackendChatWithMessages = {
  ...mockChat,
  messages: [
    { id: 1, content: 'Patient has a headache', sender: 'user', created_at: '2025-01-15T10:01:00Z' },
    { id: 2, content: 'Based on the symptoms described...', sender: 'ai', created_at: '2025-01-15T10:01:05Z' },
  ],
};

export const mockNotifications: NotificationResponse[] = [
  {
    id: 1,
    type: 'chat_assigned',
    title: 'Chat assigned',
    body: 'A new chat has been assigned to you',
    chat_id: 1,
    is_read: false,
    created_at: '2025-01-15T11:00:00Z',
  },
  {
    id: 2,
    type: 'chat_approved',
    title: 'Chat approved',
    body: 'Your chat has been approved by a specialist',
    chat_id: 2,
    is_read: true,
    created_at: '2025-01-14T09:00:00Z',
  },
];

export const mockAdminChats: AdminChatResponse[] = [
  {
    id: 1,
    title: 'Headache consultation',
    status: 'open',
    specialty: 'neurology',
    severity: 'medium',
    user_id: 1,
    owner_name: 'Dr GP',
    specialist_id: null,
    specialist_name: null,
    assigned_at: null,
    reviewed_at: null,
    review_feedback: null,
    created_at: '2025-01-15T10:00:00Z',
  },
];

export const mockAuditLogs: AuditLogResponse[] = [
  {
    id: 1,
    user_id: 1,
    user_email: 'gp@example.com',
    action: 'LOGIN',
    category: 'AUTH',
    details: 'User logged in',
    timestamp: '2025-01-15T10:00:00Z',
  },
];

// ── Handlers ──────────────────────────────────────────────────────────────

export const handlers = [
  // Auth
  http.post('/auth/login', () => {
    return HttpResponse.json(mockLoginResponse);
  }),

  http.post('/auth/register', () => {
    return HttpResponse.json({
      ...mockLoginResponse,
      user: { ...mockGPUser, full_name: 'New User' },
    });
  }),

  http.post('/auth/logout', () => {
    return HttpResponse.json({ success: true });
  }),

  http.get('/auth/me', () => {
    return HttpResponse.json(mockGPUser);
  }),

  http.patch('/auth/profile', () => {
    return HttpResponse.json(mockGPUser);
  }),

  // Chats (GP)
  http.get('/chats/', () => {
    return HttpResponse.json([mockChat, mockChat2]);
  }),

  http.get('/chats/:chatId', ({ params }) => {
    return HttpResponse.json({ ...mockChatWithMessages, id: Number(params.chatId) });
  }),

  http.post('/chats/', () => {
    return HttpResponse.json(mockChat);
  }),

  http.delete('/chats/:chatId', () => {
    return new HttpResponse(null, { status: 204 });
  }),

  http.patch('/chats/:chatId', () => {
    return HttpResponse.json(mockChat);
  }),

  http.post('/chats/:chatId/submit', () => {
    return HttpResponse.json({ ...mockChat, status: 'submitted' });
  }),

  http.post('/chats/:chatId/message', () => {
    return HttpResponse.json({ status: 'ok', ai_response: 'AI says hello' } satisfies GPMessageResponse);
  }),

  // Specialist
  http.get('/specialist/queue', () => {
    return HttpResponse.json([{ ...mockChat, status: 'submitted' }]);
  }),

  http.get('/specialist/assigned', () => {
    return HttpResponse.json([{ ...mockChat2, status: 'assigned', specialist_id: 2 }]);
  }),

  http.get('/specialist/chats/:chatId', ({ params }) => {
    return HttpResponse.json({ ...mockChatWithMessages, id: Number(params.chatId) });
  }),

  http.post('/specialist/chats/:chatId/assign', () => {
    return HttpResponse.json({ ...mockChat, status: 'assigned', specialist_id: 2 });
  }),

  http.post('/specialist/chats/:chatId/review', () => {
    return HttpResponse.json({ ...mockChat, status: 'approved' });
  }),

  http.post('/specialist/chats/:chatId/message', () => {
    return HttpResponse.json({ status: 'ok', message_id: 99 });
  }),

  // Notifications
  http.get('/notifications/', () => {
    return HttpResponse.json(mockNotifications);
  }),

  http.patch('/notifications/:id/read', () => {
    return HttpResponse.json({ ...mockNotifications[0], is_read: true });
  }),

  http.patch('/notifications/read-all', () => {
    return HttpResponse.json({ marked_read: 2 });
  }),

  // Admin: Users
  http.get('/admin/users', () => {
    return HttpResponse.json([mockGPUser, mockSpecialistUser, mockAdminUser]);
  }),

  http.get('/admin/users/:userId', ({ params }) => {
    return HttpResponse.json({ ...mockGPUser, id: Number(params.userId) });
  }),

  http.patch('/admin/users/:userId', () => {
    return HttpResponse.json(mockGPUser);
  }),

  http.delete('/admin/users/:userId', () => {
    return HttpResponse.json({ ...mockGPUser, is_active: false });
  }),

  // Admin: Chats
  http.get('/admin/chats', () => {
    return HttpResponse.json(mockAdminChats);
  }),

  http.get('/admin/chats/:chatId', ({ params }) => {
    return HttpResponse.json({ ...mockChatWithMessages, id: Number(params.chatId) });
  }),

  // Admin: Audit Logs
  http.get('/admin/audit-logs', () => {
    return HttpResponse.json(mockAuditLogs);
  }),

  // Health
  http.get('/health', () => {
    return HttpResponse.json({ status: 'ok', system: 'healthy' });
  }),
];
