import { http, HttpResponse } from 'msw';
import type { LoginResponse, UserProfile, BackendChat, BackendChatWithMessages, GPMessageResponse, NotificationResponse, AdminChatResponse, AuditLogResponse, RagStatusResponse } from '@/types/api';
import type { AdminStatsResponse } from '@/types/api';
import type { IngestionReport } from '@/services/api';

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
    owner_identifier: 'gp_1',
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
    user_identifier: 'gp_1',
    action: 'LOGIN',
    category: 'AUTH',
    details: 'User logged in',
    timestamp: '2025-01-15T10:00:00Z',
  },
];

export const mockAdminStats: AdminStatsResponse = {
  total_ai_responses: 24,
  rag_grounded_responses: 18,
  specialist_responses: 6,
  active_consultations: 7,
  active_users_by_role: {
    gp: 5,
    specialist: 2,
    admin: 1,
  },
  chats_by_status: {
    open: 2,
    submitted: 2,
    assigned: 1,
    reviewing: 1,
    approved: 1,
  },
  chats_by_specialty: {
    neurology: 4,
    rheumatology: 3,
  },
  daily_ai_queries: [
    { date: '2025-01-15', count: 3 },
    { date: '2025-01-16', count: 4 },
  ],
};

export const mockIngestionReport: IngestionReport = {
  source_name: 'NICE',
  filename: 'guideline.pdf',
  files_scanned: 1,
  files_succeeded: 1,
  files_failed: 0,
  total_chunks: 12,
  embeddings_succeeded: 12,
  embeddings_failed: 0,
  db: {
    inserted: 10,
    updated: 2,
    skipped: 0,
    failed: 0,
  },
};

export const mockRagStatus: RagStatusResponse = {
  service_status: 'healthy',
  documents: [
    {
      doc_id: 'doc-001',
      source_name: 'NICE CG1',
      chunk_count: 42,
      latest_ingestion: '2025-01-15T10:00:00Z',
    },
  ],
  jobs: {
    pending: 1,
    running: 0,
    failed: 0,
  },
};

export const handlers = [
  http.post('/auth/login', async ({ request }) => {
    const form = await request.formData();
    const email = String(form.get('username') ?? mockGPUser.email);
    return HttpResponse.json({
      ...mockLoginResponse,
      user: {
        ...mockGPUser,
        email,
        full_name: email === mockAdminUser.email
          ? mockAdminUser.full_name
          : email === mockSpecialistUser.email
            ? mockSpecialistUser.full_name
            : mockGPUser.full_name,
        role: email === mockAdminUser.email
          ? 'admin'
          : email === mockSpecialistUser.email
            ? 'specialist'
            : 'gp',
        specialty: email === mockSpecialistUser.email ? mockSpecialistUser.specialty : null,
      },
    });
  }),

  http.post('/auth/register', async ({ request }) => {
    const body = await request.json() as Partial<UserProfile> & { email?: string; role?: string; full_name?: string };
    return HttpResponse.json({
      ...mockLoginResponse,
      user: {
        ...mockGPUser,
        email: body.email ?? mockGPUser.email,
        full_name: body.full_name ?? 'New User',
        role: (body.role as UserProfile['role']) ?? 'gp',
      },
      requires_email_verification: false,
      message: 'Registration successful',
    });
  }),

  http.post('/auth/resend-verification', () => {
    return HttpResponse.json({
      message: 'If an account exists and requires verification, a verification link will be sent shortly',
    });
  }),

  http.post('/auth/verify-email/confirm', () => {
    return HttpResponse.json({ message: 'Email verified successfully' });
  }),

  http.get('/auth/verification-status', () => {
    return HttpResponse.json({
      email: 'gp@example.com',
      email_verified: true,
      email_verified_at: '2025-01-15T10:00:00Z',
    });
  }),

  http.post('/auth/forgot-password', () => {
    return HttpResponse.json({
      message: 'If that email is registered, a password reset link will be sent shortly',
    });
  }),

  http.post('/auth/reset-password/confirm', () => {
    return HttpResponse.json({ message: 'Password reset successful' });
  }),

  http.post('/auth/logout', () => {
    return HttpResponse.json({ success: true });
  }),

  http.post('/auth/refresh', () => {
    const role = localStorage.getItem('user_role') ?? mockGPUser.role;
    const email = localStorage.getItem('user_email') ?? mockGPUser.email;
    const username = localStorage.getItem('username');

    return HttpResponse.json({
      ...mockLoginResponse,
      user: {
        ...mockGPUser,
        email,
        full_name: username,
        role: role as UserProfile['role'],
        specialty: role === 'specialist' ? mockSpecialistUser.specialty : null,
      },
    });
  }),

  http.get('/auth/me', () => {
    const role = localStorage.getItem('user_role') ?? mockGPUser.role;
    const email = localStorage.getItem('user_email') ?? mockGPUser.email;
    const username = localStorage.getItem('username');
    return HttpResponse.json({
      ...mockGPUser,
      email,
      full_name: username,
      role: role as UserProfile['role'],
      specialty: role === 'specialist' ? mockSpecialistUser.specialty : null,
    });
  }),

  http.patch('/auth/profile', () => {
    return HttpResponse.json(mockGPUser);
  }),

  http.get('/chats/', ({ request }) => {
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
    return HttpResponse.json({ ...mockChat2, status: 'submitted' });
  }),

  http.post('/chats/:chatId/message', () => {
    const response: GPMessageResponse = {
      status: 'success',
      ai_response: 'AI says hello',
      ai_generating: false,
    };
    return HttpResponse.json(response);
  }),

  http.post('/chats/:chatId/files', () => {
    return HttpResponse.json({
      id: 1,
      filename: 'upload.pdf',
      file_type: 'application/pdf',
      file_size: 1234,
      created_at: '2025-01-15T10:00:00Z',
    });
  }),

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
    return HttpResponse.json({ ...mockChat2, status: 'assigned', specialist_id: 2 });
  }),

  http.post('/specialist/chats/:chatId/review', () => {
    return HttpResponse.json({ ...mockChat2, status: 'approved', specialist_id: 2 });
  }),

  http.post('/specialist/chats/:chatId/messages/:messageId/review', () => {
    return HttpResponse.json({ ...mockChat2, status: 'reviewing', specialist_id: 2 });
  }),

  http.post('/specialist/chats/:chatId/message', () => {
    return HttpResponse.json({ status: 'Message sent', message_id: 99 });
  }),

  http.get('/notifications/', () => HttpResponse.json(mockNotifications)),
  http.patch('/notifications/:notificationId/read', ({ params }) =>
    HttpResponse.json({
      ...mockNotifications[0],
      id: Number(params.notificationId),
      is_read: true,
    })),
  http.patch('/notifications/read-all', () => HttpResponse.json({ marked_read: 2 })),

  http.get('/admin/users', () => HttpResponse.json([mockGPUser, mockSpecialistUser, mockAdminUser])),
  http.get('/admin/users/:userId', ({ params }) => {
    const userId = Number(params.userId);
    const user = [mockGPUser, mockSpecialistUser, mockAdminUser].find(u => u.id === userId) ?? mockGPUser;
    return HttpResponse.json(user);
  }),
  http.patch('/admin/users/:userId', () => HttpResponse.json(mockGPUser)),
  http.delete('/admin/users/:userId', ({ params }) =>
    HttpResponse.json({
      ...mockGPUser,
      id: Number(params.userId),
      is_active: false,
    })),

  http.get('/admin/chats', () => HttpResponse.json(mockAdminChats)),
  http.get('/admin/chats/:chatId', ({ params }) =>
    HttpResponse.json({
      ...mockAdminChats[0],
      id: Number(params.chatId),
      messages: mockChatWithMessages.messages,
    })),
  http.patch('/admin/chats/:chatId', () => HttpResponse.json(mockAdminChats[0])),
  http.delete('/admin/chats/:chatId', () => new HttpResponse(null, { status: 204 })),

  http.get('/admin/stats', () => HttpResponse.json(mockAdminStats)),
  http.get('/admin/logs', () => HttpResponse.json(mockAuditLogs)),
  http.post('/admin/guidelines/upload', () => HttpResponse.json(mockIngestionReport)),

  http.get('/admin/rag/status', () => HttpResponse.json(mockRagStatus)),

  http.get('/health', () => HttpResponse.json({ status: 'healthy' })),
];
