import { http, HttpResponse } from 'msw';
import type { LoginResponse, UserProfile, BackendChat, BackendChatWithMessages, GPMessageResponse, NotificationResponse, AdminChatResponse, AuditLogResponse } from '../../types/api';

// Must match VITE_API_URL in .env.local so MSW intercepts absolute fetch calls
const API = 'http://localhost:8000';

// ── Fixture data ──────────────────────────────────────────────────────────

export const mockGPUser: UserProfile = {
  id: 1,
  email: 'gp@example.com',
  full_name: 'Dr GP',
  role: 'gp',
  specialty: null,
  is_active: true,
  email_verified: true,
};

export const mockSpecialistUser: UserProfile = {
  id: 2,
  email: 'specialist@example.com',
  full_name: 'Dr Specialist',
  role: 'specialist',
  specialty: 'neurology',
  is_active: true,
  email_verified: true,
};

export const mockAdminUser: UserProfile = {
  id: 3,
  email: 'admin@example.com',
  full_name: 'Admin User',
  role: 'admin',
  specialty: null,
  is_active: true,
  email_verified: true,
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
    owner_identifier: 'Dr GP',
    specialist_id: null,
    specialist_identifier: null,
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
    user_identifier: 'gp@example.com',
    action: 'LOGIN',
    category: 'AUTH',
    details: 'User logged in',
    timestamp: '2025-01-15T10:00:00Z',
  },
];

// ── Handlers ──────────────────────────────────────────────────────────────

export const handlers = [
  // Auth
  http.post(`${API}/auth/login`, () => {
    return HttpResponse.json(mockLoginResponse);
  }),

  http.post(`${API}/auth/register`, () => {
    return HttpResponse.json({
      ...mockLoginResponse,
      user: { ...mockGPUser, full_name: 'New User' },
      requires_email_verification: false,
      message: 'Registration successful',
    });
  }),

  http.post(`${API}/auth/resend-verification`, () => {
    return HttpResponse.json({
      message: 'If an account exists and requires verification, a verification link will be sent shortly',
    });
  }),

  http.post(`${API}/auth/verify-email/confirm`, () => {
    return HttpResponse.json({ message: 'Email verified successfully' });
  }),

  http.get(`${API}/auth/verification-status`, () => {
    return HttpResponse.json({
      email: 'gp@example.com',
      email_verified: true,
      email_verified_at: '2025-01-15T10:00:00Z',
    });
  }),

  http.post(`${API}/auth/forgot-password`, () => {
    return HttpResponse.json({
      message: 'If that email is registered, a password reset link will be sent shortly',
    });
  }),

  http.post(`${API}/auth/reset-password/confirm`, () => {
    return HttpResponse.json({ message: 'Password reset successful' });
  }),

  http.post(`${API}/auth/logout`, () => {
    return HttpResponse.json({ success: true });
  }),

  http.get(`${API}/auth/me`, () => {
    return HttpResponse.json(mockGPUser);
  }),

  http.patch(`${API}/auth/profile`, () => {
    return HttpResponse.json(mockGPUser);
  }),

  // Chats (GP)
  http.get(`${API}/chats/`, ({ request }) => {
    const url = new URL(request.url);
    let chats = [mockChat, mockChat2];
    const search = url.searchParams.get('search');
    if (search) {
      chats = chats.filter(c => c.title.toLowerCase().includes(search.toLowerCase()));
    }
    const specialty = url.searchParams.get('specialty');
    if (specialty) {
      chats = chats.filter(c => c.specialty === specialty);
    }
    return HttpResponse.json(chats);
  }),

  http.get(`${API}/chats/:chatId`, ({ params }) => {
    return HttpResponse.json({ ...mockChatWithMessages, id: Number(params.chatId) });
  }),

  http.post(`${API}/chats/`, () => {
    return HttpResponse.json(mockChat);
  }),

  http.delete(`${API}/chats/:chatId`, () => {
    return new HttpResponse(null, { status: 204 });
  }),

  http.patch(`${API}/chats/:chatId`, () => {
    return HttpResponse.json(mockChat);
  }),

  http.post(`${API}/chats/:chatId/submit`, () => {
    return HttpResponse.json({ ...mockChat, status: 'submitted' });
  }),

  http.post(`${API}/chats/:chatId/message`, () => {
    return HttpResponse.json({ status: 'ok', ai_response: 'AI says hello' } satisfies GPMessageResponse);
  }),

  // Specialist
  http.get(`${API}/specialist/queue`, () => {
    return HttpResponse.json([{ ...mockChat, status: 'submitted' }]);
  }),

  http.get(`${API}/specialist/assigned`, () => {
    return HttpResponse.json([{ ...mockChat2, status: 'assigned', specialist_id: 2 }]);
  }),

  http.get(`${API}/specialist/chats/:chatId`, ({ params }) => {
    return HttpResponse.json({ ...mockChatWithMessages, id: Number(params.chatId) });
  }),

  http.post(`${API}/specialist/chats/:chatId/assign`, () => {
    return HttpResponse.json({ ...mockChat, status: 'assigned', specialist_id: 2 });
  }),

  http.post(`${API}/specialist/chats/:chatId/review`, () => {
    return HttpResponse.json({ ...mockChat, status: 'approved' });
  }),

  http.post(`${API}/specialist/chats/:chatId/message`, () => {
    return HttpResponse.json({ status: 'ok', message_id: 99 });
  }),

  // Notifications
  http.get(`${API}/notifications/`, () => {
    return HttpResponse.json(mockNotifications);
  }),

  http.patch(`${API}/notifications/:id/read`, () => {
    return HttpResponse.json({ ...mockNotifications[0], is_read: true });
  }),

  http.patch(`${API}/notifications/read-all`, () => {
    return HttpResponse.json({ marked_read: 2 });
  }),

  // Admin: Users
  http.get(`${API}/admin/users`, () => {
    return HttpResponse.json([mockGPUser, mockSpecialistUser, mockAdminUser]);
  }),

  http.get(`${API}/admin/users/:userId`, ({ params }) => {
    return HttpResponse.json({ ...mockGPUser, id: Number(params.userId) });
  }),

  http.patch(`${API}/admin/users/:userId`, () => {
    return HttpResponse.json(mockGPUser);
  }),

  http.delete(`${API}/admin/users/:userId`, () => {
    return HttpResponse.json({ ...mockGPUser, is_active: false });
  }),

  // Admin: Chats
  http.get(`${API}/admin/chats`, () => {
    return HttpResponse.json(mockAdminChats);
  }),

  http.get(`${API}/admin/chats/:chatId`, ({ params }) => {
    return HttpResponse.json({ ...mockChatWithMessages, id: Number(params.chatId) });
  }),

  // Admin: Audit Logs
  http.get(`${API}/admin/audit-logs`, () => {
    return HttpResponse.json(mockAuditLogs);
  }),

  // Health
  http.get(`${API}/health`, () => {
    return HttpResponse.json({ status: 'ok', system: 'healthy' });
  }),
];
