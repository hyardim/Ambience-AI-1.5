import { describe, it, expect, vi, beforeEach } from 'vitest';
import { http, HttpResponse } from 'msw';
import { server } from '../test/mocks/server';
import {
  login,
  register,
  logout,
  getProfile,
  updateProfile,
  getChats,
  getChat,
  createChat,
  deleteChat,
  updateChat,
  submitForReview,
  sendMessage,
  getSpecialistQueue,
  getAssignedChats,
  getSpecialistChatDetail,
  assignChat,
  reviewChat,
  sendSpecialistMessage,
  getNotifications,
  markNotificationRead,
  markAllNotificationsRead,
  adminGetUsers,
  adminUpdateUser,
  adminDeactivateUser,
  adminGetChats,
  healthCheck,
} from './api';

describe('API service', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  // ── Auth ──────────────────────────────────────────────────────────────

  describe('login()', () => {
    it('sends form-urlencoded credentials and returns LoginResponse', async () => {
      const data = await login('gp@example.com', 'password123');
      expect(data.access_token).toBe('mock-jwt-token');
      expect(data.user.email).toBe('gp@example.com');
    });

    it('throws on invalid credentials', async () => {
      server.use(
        http.post('/auth/login', () => {
          return HttpResponse.json({ detail: 'Invalid credentials' }, { status: 401 });
        }),
      );
      // 401 triggers the session-expiry path; override to plain 400 for this test
      server.use(
        http.post('/auth/login', () => {
          return HttpResponse.json({ detail: 'Bad creds' }, { status: 400 });
        }),
      );
      await expect(login('bad', 'creds')).rejects.toThrow('Bad creds');
    });
  });

  describe('register()', () => {
    it('sends JSON and returns LoginResponse', async () => {
      const data = await register({
        email: 'new@example.com',
        password: 'pass',
        role: 'gp',
      });
      expect(data.access_token).toBe('mock-jwt-token');
    });
  });

  describe('logout()', () => {
    it('calls POST /auth/logout', async () => {
      localStorage.setItem('access_token', 'tok');
      const data = await logout();
      expect(data.success).toBe(true);
    });
  });

  // ── Profile ───────────────────────────────────────────────────────────

  describe('getProfile()', () => {
    it('returns the user profile', async () => {
      localStorage.setItem('access_token', 'tok');
      const data = await getProfile();
      expect(data.email).toBe('gp@example.com');
    });
  });

  describe('updateProfile()', () => {
    it('sends PATCH and returns updated profile', async () => {
      localStorage.setItem('access_token', 'tok');
      const data = await updateProfile({ full_name: 'Updated' });
      expect(data.email).toBe('gp@example.com');
    });
  });

  // ── Chats (GP) ────────────────────────────────────────────────────────

  describe('getChats()', () => {
    it('returns array of chats', async () => {
      localStorage.setItem('access_token', 'tok');
      const chats = await getChats();
      expect(chats).toHaveLength(2);
      expect(chats[0].title).toBe('Headache consultation');
    });
  });

  describe('getChat()', () => {
    it('returns chat with messages', async () => {
      localStorage.setItem('access_token', 'tok');
      const chat = await getChat(1);
      expect(chat.messages).toHaveLength(2);
    });
  });

  describe('createChat()', () => {
    it('creates a new chat', async () => {
      localStorage.setItem('access_token', 'tok');
      const chat = await createChat({ title: 'Test', specialty: 'neurology' });
      expect(chat.id).toBe(1);
    });
  });

  describe('deleteChat()', () => {
    it('succeeds with 204', async () => {
      localStorage.setItem('access_token', 'tok');
      await expect(deleteChat(1)).resolves.toBeUndefined();
    });
  });

  describe('updateChat()', () => {
    it('sends PATCH and returns updated chat', async () => {
      localStorage.setItem('access_token', 'tok');
      const chat = await updateChat(1, { title: 'Updated' });
      expect(chat.id).toBe(1);
    });
  });

  describe('submitForReview()', () => {
    it('submits a chat and returns updated status', async () => {
      localStorage.setItem('access_token', 'tok');
      const chat = await submitForReview(1);
      expect(chat.status).toBe('submitted');
    });
  });

  describe('sendMessage()', () => {
    it('sends message and returns AI response', async () => {
      localStorage.setItem('access_token', 'tok');
      const res = await sendMessage(1, 'Hello');
      expect(res.ai_response).toBe('AI says hello');
    });
  });

  // ── Specialist ────────────────────────────────────────────────────────

  describe('getSpecialistQueue()', () => {
    it('returns queue chats', async () => {
      localStorage.setItem('access_token', 'tok');
      const chats = await getSpecialistQueue();
      expect(chats).toHaveLength(1);
      expect(chats[0].status).toBe('submitted');
    });
  });

  describe('getAssignedChats()', () => {
    it('returns assigned chats', async () => {
      localStorage.setItem('access_token', 'tok');
      const chats = await getAssignedChats();
      expect(chats).toHaveLength(1);
    });
  });

  describe('getSpecialistChatDetail()', () => {
    it('returns chat with messages', async () => {
      localStorage.setItem('access_token', 'tok');
      const chat = await getSpecialistChatDetail(1);
      expect(chat.messages).toHaveLength(2);
    });
  });

  describe('assignChat()', () => {
    it('assigns chat to specialist', async () => {
      localStorage.setItem('access_token', 'tok');
      const chat = await assignChat(1, 2);
      expect(chat.specialist_id).toBe(2);
    });
  });

  describe('reviewChat()', () => {
    it('approves a chat', async () => {
      localStorage.setItem('access_token', 'tok');
      const chat = await reviewChat(1, 'approve', 'Looks good');
      expect(chat.status).toBe('approved');
    });
  });

  describe('sendSpecialistMessage()', () => {
    it('sends specialist message', async () => {
      localStorage.setItem('access_token', 'tok');
      const res = await sendSpecialistMessage(1, 'Hello from specialist');
      expect(res.message_id).toBe(99);
    });
  });

  // ── Notifications ─────────────────────────────────────────────────────

  describe('getNotifications()', () => {
    it('returns notifications list', async () => {
      localStorage.setItem('access_token', 'tok');
      const notifs = await getNotifications();
      expect(notifs).toHaveLength(2);
    });
  });

  describe('markNotificationRead()', () => {
    it('marks a notification as read', async () => {
      localStorage.setItem('access_token', 'tok');
      const notif = await markNotificationRead(1);
      expect(notif.is_read).toBe(true);
    });
  });

  describe('markAllNotificationsRead()', () => {
    it('returns count of marked notifications', async () => {
      localStorage.setItem('access_token', 'tok');
      const res = await markAllNotificationsRead();
      expect(res.marked_read).toBe(2);
    });
  });

  // ── Admin ─────────────────────────────────────────────────────────────

  describe('adminGetUsers()', () => {
    it('returns user list', async () => {
      localStorage.setItem('access_token', 'tok');
      const users = await adminGetUsers();
      expect(users).toHaveLength(3);
    });
  });

  describe('adminUpdateUser()', () => {
    it('updates a user', async () => {
      localStorage.setItem('access_token', 'tok');
      const user = await adminUpdateUser(1, { full_name: 'Updated' });
      expect(user.email).toBe('gp@example.com');
    });
  });

  describe('adminDeactivateUser()', () => {
    it('deactivates a user', async () => {
      localStorage.setItem('access_token', 'tok');
      const user = await adminDeactivateUser(1);
      expect(user.is_active).toBe(false);
    });
  });

  describe('adminGetChats()', () => {
    it('returns admin chat list', async () => {
      localStorage.setItem('access_token', 'tok');
      const chats = await adminGetChats();
      expect(chats).toHaveLength(1);
    });
  });

  // ── Health ────────────────────────────────────────────────────────────

  describe('healthCheck()', () => {
    it('returns health status', async () => {
      const data = await healthCheck();
      expect(data.status).toBe('ok');
    });
  });

  // ── Error handling ────────────────────────────────────────────────────

  describe('handleResponse error paths', () => {
    it('throws with parsed detail message on non-ok JSON response', async () => {
      server.use(
        http.get('/health', () => {
          return HttpResponse.json({ detail: 'Server error' }, { status: 500 });
        }),
      );
      await expect(healthCheck()).rejects.toThrow('Server error');
    });

    it('throws with raw text when response is not JSON', async () => {
      server.use(
        http.get('/health', () => {
          return new HttpResponse('Something broke', { status: 500 });
        }),
      );
      await expect(healthCheck()).rejects.toThrow('Something broke');
    });

    it('clears localStorage and redirects on 401', async () => {
      localStorage.setItem('access_token', 'tok');

      server.use(
        http.get('/chats/', () => {
          return HttpResponse.json({ detail: 'Unauthorized' }, { status: 401 });
        }),
      );

      // handleResponse clears localStorage then sets window.location.href = '/login'
      // In jsdom, the href assignment may throw 'Invalid URL', so we just
      // verify that the promise rejects and localStorage is cleared.
      await expect(getChats()).rejects.toThrow();
      expect(localStorage.getItem('access_token')).toBeNull();
      expect(localStorage.getItem('username')).toBeNull();
      expect(localStorage.getItem('user_role')).toBeNull();
    });
  });
});
