import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '@test/mocks/server';
import {
  adminDeactivateUser,
  adminDeleteChat,
  adminGetChat,
  adminGetChats,
  adminGetLogs,
  adminGetStats,
  adminGetUser,
  adminGetUsers,
  adminUpdateChat,
  adminUpdateUser,
  adminUploadGuideline,
  assignChat,
  createChat,
  deleteChat,
  getAssignedChats,
  getChat,
  getChats,
  getNotifications,
  getProfile,
  getSpecialistChatDetail,
  getSpecialistQueue,
  healthCheck,
  login,
  logout,
  markAllNotificationsRead,
  markNotificationRead,
  register,
  resetPassword,
  reviewChat,
  reviewMessage,
  sendMessage,
  sendSpecialistMessage,
  submitForReview,
  subscribeToChatStream,
  updateChat,
  updateProfile,
  uploadChatFile,
} from '@/services/api';

class MockEventSource {
  static instances: MockEventSource[] = [];

  url: string;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  listeners = new Map<string, ((event: MessageEvent) => void)[]>();
  close = vi.fn();

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    const listeners = this.listeners.get(type) ?? [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  emit(type: string, payload: unknown) {
    const event = {
      data: typeof payload === 'string' ? payload : JSON.stringify(payload),
    } as MessageEvent;

    for (const listener of this.listeners.get(type) ?? []) {
      listener(event);
    }
  }
}

describe('API service', () => {
  beforeEach(() => {
    localStorage.clear();
    MockEventSource.instances = [];
    vi.stubGlobal('EventSource', MockEventSource as unknown as typeof EventSource);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  describe('auth and profile', () => {
    it('logs in with form-urlencoded credentials', async () => {
      const data = await login('gp@example.com', 'password123');
      expect(data.access_token).toBe('mock-jwt-token');
      expect(data.user.email).toBe('gp@example.com');
    });

    it('surfaces non-401 login failures', async () => {
      server.use(
        http.post('/auth/login', () =>
          HttpResponse.json({ detail: 'Bad creds' }, { status: 400 })),
      );

      await expect(login('bad', 'creds')).rejects.toThrow('Bad creds');
    });

    it('registers a user and resets password', async () => {
      const loginResponse = await register({
        email: 'new@example.com',
        password: 'pass',
        role: 'gp',
      });
      const resetResponse = await resetPassword('new@example.com', 'Password1!');

      expect(loginResponse.access_token).toBe('mock-jwt-token');
      expect(resetResponse.message).toMatch(/password reset successful/i);
    });

    it('logs out and loads/updates profile', async () => {
      localStorage.setItem('access_token', 'tok');

      await expect(logout()).resolves.toEqual({ success: true });
      await expect(getProfile()).resolves.toMatchObject({ email: 'gp@example.com' });
      await expect(updateProfile({ full_name: 'Updated' })).resolves.toMatchObject({
        email: 'gp@example.com',
      });
    });

    it('omits auth headers when no token exists', async () => {
      server.use(
        http.get('/auth/me', ({ request }) => {
          expect(request.headers.get('authorization')).toBeNull();
          return HttpResponse.json({
            id: 1,
            email: 'gp@example.com',
            full_name: 'Dr GP',
            role: 'gp',
            specialty: null,
            is_active: true,
          });
        }),
      );

      await expect(getProfile()).resolves.toMatchObject({ email: 'gp@example.com' });
    });

    it('surfaces plain-text errors and redirects on 401 responses', async () => {
      server.use(
        http.get('/auth/me', () => new HttpResponse('Plain failure', { status: 500 })),
      );
      await expect(getProfile()).rejects.toThrow('Plain failure');

      localStorage.setItem('access_token', 'tok');
      localStorage.setItem('username', 'Dr GP');
      localStorage.setItem('user_role', 'gp');
      localStorage.setItem('user_email', 'gp@example.com');

      server.use(
        http.get('/auth/me', () => HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 })),
      );

      await expect(getProfile()).rejects.toThrow('Session expired');
      expect(localStorage.getItem('access_token')).toBeNull();
      expect(window.location.pathname).toBe('/login');
    });
  });

  describe('gp chat APIs', () => {
    it('gets chats with filters and chat detail', async () => {
      localStorage.setItem('access_token', 'tok');

      const chats = await getChats({
        status: 'submitted',
        specialty: 'rheumatology',
        search: 'joint',
        date_from: '2025-01-01',
        date_to: '2025-01-31',
        skip: 5,
        limit: 10,
      });
      const chat = await getChat(1);

      expect(chats).toHaveLength(1);
      expect(chats[0].title).toMatch(/joint pain/i);
      expect(chat.messages).toHaveLength(2);
    });

    it('creates, updates, submits, deletes, uploads, and sends messages for chats', async () => {
      localStorage.setItem('access_token', 'tok');
      server.use(
        http.post('/chats/:chatId/files', () =>
          HttpResponse.json({ id: 'file-1', name: 'report.pdf', size: '2MB', type: 'pdf' })),
      );

      await expect(createChat({ title: 'Test', specialty: 'neurology' })).resolves.toMatchObject({ id: 1 });
      await expect(updateChat(1, { title: 'Updated' })).resolves.toMatchObject({ id: 1 });
      await expect(submitForReview(1)).resolves.toMatchObject({ status: 'submitted' });
      await expect(sendMessage(1, 'Hello')).resolves.toMatchObject({ ai_response: 'AI says hello' });
      await expect(uploadChatFile(1, new File(['hello'], 'report.pdf', { type: 'application/pdf' }))).resolves.toMatchObject({ name: 'report.pdf' });
      await expect(deleteChat(1)).resolves.toBeUndefined();
    });
  });

  describe('specialist APIs', () => {
    it('gets specialist queues and chat detail', async () => {
      localStorage.setItem('access_token', 'tok');

      await expect(getSpecialistQueue()).resolves.toHaveLength(1);
      await expect(getAssignedChats()).resolves.toHaveLength(1);
      await expect(getSpecialistChatDetail(1)).resolves.toMatchObject({
        messages: expect.any(Array),
      });
    });

    it('assigns, reviews, reviews messages, and sends specialist messages', async () => {
      localStorage.setItem('access_token', 'tok');
      server.use(
        http.post('/specialist/chats/:chatId/messages/:messageId/review', async ({ request }) => {
          const body = await request.json() as Record<string, unknown>;
          expect(body.action).toBe('manual_response');
          expect(body.feedback).toBe('Needs correction');
          expect(body.replacement_content).toBe('Replacement');
          expect(body.replacement_sources).toEqual(['NICE']);
          return HttpResponse.json({ status: 'reviewing' });
        }),
      );

      await expect(assignChat(1, 2)).resolves.toMatchObject({ specialist_id: 2 });
      await expect(reviewChat(1, 'approve', 'Looks good')).resolves.toMatchObject({ status: 'approved' });
      await expect(
        reviewMessage(1, 2, 'manual_response', 'Needs correction', 'Replacement', ['NICE']),
      ).resolves.toMatchObject({ status: 'reviewing' });
      await expect(sendSpecialistMessage(1, 'Hello from specialist')).resolves.toMatchObject({ message_id: 99 });
    });
  });

  describe('notifications', () => {
    it('loads notifications and respects unread-only filter', async () => {
      localStorage.setItem('access_token', 'tok');
      server.use(
        http.get('/notifications/', ({ request }) => {
          const url = new URL(request.url);
          if (url.searchParams.get('unread_only') === 'true') {
            return HttpResponse.json([]);
          }
          return HttpResponse.json([
            {
              id: 1,
              type: 'chat_assigned',
              title: 'Chat assigned',
              body: 'A new chat has been assigned to you',
              chat_id: 1,
              is_read: false,
              created_at: '2025-01-15T11:00:00Z',
            },
          ]);
        }),
      );

      await expect(getNotifications()).resolves.toHaveLength(1);
      await expect(getNotifications(true)).resolves.toEqual([]);
      await expect(markNotificationRead(1)).resolves.toMatchObject({ is_read: true });
      await expect(markAllNotificationsRead()).resolves.toEqual({ marked_read: 2 });
    });
  });

  describe('admin APIs', () => {
    it('loads users and supports role-filtered queries and updates', async () => {
      localStorage.setItem('access_token', 'tok');
      server.use(
        http.get('/admin/users', ({ request }) => {
          const url = new URL(request.url);
          if (url.searchParams.get('role') === 'specialist') {
            return HttpResponse.json([]);
          }
          return HttpResponse.json([
            { id: 1, email: 'gp@example.com', full_name: 'Dr GP', role: 'gp', specialty: null, is_active: true },
          ]);
        }),
      );

      await expect(adminGetUsers()).resolves.toHaveLength(1);
      await expect(adminGetUsers('specialist')).resolves.toEqual([]);
      await expect(adminGetUser(1)).resolves.toMatchObject({ email: 'gp@example.com' });
      await expect(adminUpdateUser(1, { full_name: 'Updated' })).resolves.toMatchObject({ email: 'gp@example.com' });
      await expect(adminDeactivateUser(1)).resolves.toMatchObject({ is_active: false });
    });

    it('includes optional pagination and limit filters when provided', async () => {
      localStorage.setItem('access_token', 'tok');
      server.use(
        http.get('/admin/chats', ({ request }) => {
          const url = new URL(request.url);
          expect(url.searchParams.get('skip')).toBe('1');
          expect(url.searchParams.get('limit')).toBe('10');
          return HttpResponse.json([]);
        }),
        http.get('/admin/logs', ({ request }) => {
          const url = new URL(request.url);
          expect(url.searchParams.get('limit')).toBe('5');
          return HttpResponse.json([]);
        }),
      );

      await expect(adminGetChats({ skip: 1, limit: 10 })).resolves.toEqual([]);
      await expect(adminGetLogs({ limit: 5 })).resolves.toEqual([]);
    });

    it('loads, filters, mutates, and deletes chats plus dashboard data', async () => {
      localStorage.setItem('access_token', 'tok');
      server.use(
        http.get('/admin/chats', ({ request }) => {
          const url = new URL(request.url);
          if (url.searchParams.get('status')) {
            expect(url.searchParams.get('status')).toBe('open');
            expect(url.searchParams.get('specialty')).toBe('neurology');
            expect(url.searchParams.get('user_id')).toBe('1');
            expect(url.searchParams.get('specialist_id')).toBe('2');
            expect(url.searchParams.get('limit')).toBe('25');
            return HttpResponse.json([]);
          }
          return HttpResponse.json([
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
          ]);
        }),
        http.patch('/admin/chats/:chatId', async ({ params, request }) => {
          const body = await request.json() as Record<string, unknown>;
          return HttpResponse.json({
            id: Number(params.chatId),
            title: body.title ?? 'Updated title',
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
          });
        }),
        http.delete('/admin/chats/:chatId', () => new HttpResponse(null, { status: 204 })),
      );

      await expect(adminGetChats()).resolves.toHaveLength(1);
      await expect(
        adminGetChats({
          status: 'open',
          specialty: 'neurology',
          user_id: 1,
          specialist_id: 2,
          skip: 0,
          limit: 25,
        }),
      ).resolves.toEqual([]);
      await expect(adminGetChat(1)).resolves.toMatchObject({ messages: expect.any(Array) });
      await expect(adminUpdateChat(1, { title: 'Updated title' })).resolves.toMatchObject({ title: 'Updated title' });
      await expect(adminDeleteChat(1)).resolves.toBeUndefined();
      await expect(adminGetStats()).resolves.toMatchObject({ total_ai_responses: 24 });
    });

    it('filters logs and uploads guidelines', async () => {
      localStorage.setItem('access_token', 'tok');
      server.use(
        http.get('/admin/logs', ({ request }) => {
          const url = new URL(request.url);
          if (url.searchParams.get('action')) {
            expect(url.searchParams.get('action')).toBe('LOGIN');
            expect(url.searchParams.get('category')).toBe('AUTH');
            expect(url.searchParams.get('search')).toBe('logged');
            expect(url.searchParams.get('user_id')).toBe('1');
            expect(url.searchParams.get('date_from')).toBe('2025-01-01');
            expect(url.searchParams.get('date_to')).toBe('2025-01-31');
            expect(url.searchParams.get('limit')).toBe('50');
            return HttpResponse.json([]);
          }
          return HttpResponse.json([]);
        }),
      );

      await expect(
        adminGetLogs({
          action: 'LOGIN',
          category: 'AUTH',
          search: 'logged',
          user_id: 1,
          date_from: '2025-01-01',
          date_to: '2025-01-31',
          limit: 50,
        }),
      ).resolves.toEqual([]);
      await expect(
        adminUploadGuideline(new File(['pdf'], 'guideline.pdf', { type: 'application/pdf' }), 'NICE'),
      ).resolves.toMatchObject({ source_name: 'NICE' });
    });
  });

  describe('health and error handling', () => {
    it('returns health status', async () => {
      await expect(healthCheck()).resolves.toEqual({ status: 'ok', system: 'healthy' });
    });

    it('throws with raw text when the body is not JSON', async () => {
      server.use(
        http.get('/health', () => new HttpResponse('Something broke', { status: 500 })),
      );

      await expect(healthCheck()).rejects.toThrow('Something broke');
    });

    it('clears session storage on 401 responses', async () => {
      localStorage.setItem('access_token', 'tok');
      localStorage.setItem('username', 'Dr GP');
      localStorage.setItem('user_role', 'gp');
      localStorage.setItem('user_email', 'gp@example.com');
      server.use(
        http.get('/auth/me', () => HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 })),
      );

      await expect(getProfile()).rejects.toThrow(/session expired/i);
      expect(localStorage.getItem('access_token')).toBeNull();
      expect(localStorage.getItem('username')).toBeNull();
      expect(localStorage.getItem('user_role')).toBeNull();
      expect(localStorage.getItem('user_email')).toBeNull();
      expect(window.location.pathname).toBe('/login');
    });
  });

  describe('subscribeToChatStream()', () => {
    it('reports connection errors immediately without a token', () => {
      const onConnectionError = vi.fn();
      const cleanup = subscribeToChatStream(1, { onConnectionError });

      expect(onConnectionError).toHaveBeenCalled();
      expect(cleanup).toBeTypeOf('function');
    });

    it('wires event source callbacks and cleanup', () => {
      localStorage.setItem('access_token', 'tok');
      const onOpen = vi.fn();
      const onStreamStart = vi.fn();
      const onContent = vi.fn();
      const onComplete = vi.fn();
      const onError = vi.fn();
      const onConnectionError = vi.fn();

      const cleanup = subscribeToChatStream(12, {
        onOpen,
        onStreamStart,
        onContent,
        onComplete,
        onError,
        onConnectionError,
      });

      const source = MockEventSource.instances[0];
      expect(source.url).toContain('/chats/12/stream?token=tok');

      source.onopen?.();
      source.emit('stream_start', { message_id: 7 });
      source.emit('content', { message_id: 7, content: 'partial' });
      source.emit('complete', { message_id: 7, content: 'final', citations: [{ title: 'A' }] });
      source.emit('error', { message_id: 7, error: 'boom' });
      source.emit('content', '{bad json');
      source.onerror?.();
      cleanup();

      expect(onOpen).toHaveBeenCalled();
      expect(onStreamStart).toHaveBeenCalledWith(7);
      expect(onContent).toHaveBeenCalledWith(7, 'partial');
      expect(onComplete).toHaveBeenCalledWith(7, 'final', [{ title: 'A' }]);
      expect(onError).toHaveBeenCalledWith(7, 'boom');
      expect(onConnectionError).toHaveBeenCalled();
      expect(source.close).toHaveBeenCalled();
    });

    it('falls back to empty payload values for stream content, completion, and errors', () => {
      localStorage.setItem('access_token', 'tok');
      const onContent = vi.fn();
      const onComplete = vi.fn();
      const onError = vi.fn();

      subscribeToChatStream(44, {
        onContent,
        onComplete,
        onError,
      });

      const source = MockEventSource.instances.at(-1)!;
      source.emit('content', { message_id: 9 });
      source.emit('complete', { message_id: 9 });
      source.emit('error', { message_id: 9 });

      expect(onContent).toHaveBeenCalledWith(9, '');
      expect(onComplete).toHaveBeenCalledWith(9, '', null);
      expect(onError).toHaveBeenCalledWith(9, 'Unknown error');
    });
  });
});
