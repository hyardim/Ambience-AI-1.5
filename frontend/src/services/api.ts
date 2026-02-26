import type {
  BackendChat,
  BackendChatWithMessages,
  BackendMessage,
  LoginResponse,
  RegisterRequest,
  ChatCreateRequest,
  MessageCreateRequest,
  ProfileUpdateRequest,
  UserProfile,
  AssignRequest,
  ReviewRequest,
  NotificationResponse,
  UserUpdateAdmin,
  AdminChatResponse,
  AuditLogResponse,
  ChatUpdateRequest,
} from '../types/api';

const API_BASE = import.meta.env.VITE_API_URL || '';

// ── Helper ──────────────────────────────────────────────────────────────

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('access_token');
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (res.status === 401) {
    localStorage.removeItem('access_token');
    localStorage.removeItem('username');
    localStorage.removeItem('user_role');
    localStorage.removeItem('user_email');
    window.location.href = '/login';
    throw new Error('Session expired');
  }
  if (!res.ok) {
    const rawBody = await res.text();
    let errorMessage = rawBody || `Request failed (${res.status})`;

    try {
      const parsed = JSON.parse(rawBody) as { detail?: string };
      if (parsed?.detail) {
        errorMessage = parsed.detail;
      }
    } catch {
      // Keep raw text fallback when body is not JSON.
    }

    throw new Error(errorMessage);
  }
  // 204 No Content
  if (res.status === 204) return undefined as unknown as T;
  return res.json();
}

// ── Auth ─────────────────────────────────────────────────────────────────

export async function login(username: string, password: string): Promise<LoginResponse> {
  const body = new URLSearchParams();
  body.append('username', username);
  body.append('password', password);

  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });

  return handleResponse<LoginResponse>(res);
}

export async function register(payload: RegisterRequest): Promise<LoginResponse> {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  return handleResponse<LoginResponse>(res);
}

// ── Profile ──────────────────────────────────────────────────────────────

export async function getProfile(): Promise<UserProfile> {
  const res = await fetch(`${API_BASE}/auth/me`, {
    headers: authHeaders(),
  });
  return handleResponse<UserProfile>(res);
}

export async function updateProfile(data: ProfileUpdateRequest): Promise<UserProfile> {
  const res = await fetch(`${API_BASE}/auth/profile`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(data),
  });
  return handleResponse<UserProfile>(res);
}

// ── Chats (GP) ───────────────────────────────────────────────────────────

export async function getChats(skip = 0, limit = 100): Promise<BackendChat[]> {
  const params = new URLSearchParams({ skip: String(skip), limit: String(limit) });
  const res = await fetch(`${API_BASE}/chats/?${params}`, {
    headers: authHeaders(),
  });
  return handleResponse<BackendChat[]>(res);
}

export async function getChat(chatId: number): Promise<BackendChatWithMessages> {
  const res = await fetch(`${API_BASE}/chats/${chatId}`, {
    headers: authHeaders(),
  });
  return handleResponse<BackendChatWithMessages>(res);
}

export async function createChat(data: ChatCreateRequest): Promise<BackendChat> {
  const res = await fetch(`${API_BASE}/chats/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(data),
  });
  return handleResponse<BackendChat>(res);
}

export async function deleteChat(chatId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/chats/${chatId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  return handleResponse<void>(res);
}

export async function submitForReview(chatId: number): Promise<BackendChat> {
  const res = await fetch(`${API_BASE}/chats/${chatId}/submit`, {
    method: 'POST',
    headers: authHeaders(),
  });
  return handleResponse<BackendChat>(res);
}

export async function sendMessage(
  chatId: number,
  content: string,
): Promise<BackendMessage> {
  const body: MessageCreateRequest = { role: 'user', content };
  const res = await fetch(`${API_BASE}/chats/${chatId}/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  return handleResponse<BackendMessage>(res);
}

// ── Specialist ───────────────────────────────────────────────────────────

export async function getSpecialistQueue(): Promise<BackendChat[]> {
  const res = await fetch(`${API_BASE}/specialist/queue`, {
    headers: authHeaders(),
  });
  return handleResponse<BackendChat[]>(res);
}

export async function getAssignedChats(): Promise<BackendChat[]> {
  const res = await fetch(`${API_BASE}/specialist/assigned`, {
    headers: authHeaders(),
  });
  return handleResponse<BackendChat[]>(res);
}

export async function getSpecialistChatDetail(chatId: number): Promise<BackendChatWithMessages> {
  const res = await fetch(`${API_BASE}/specialist/chats/${chatId}`, {
    headers: authHeaders(),
  });
  return handleResponse<BackendChatWithMessages>(res);
}

export async function assignChat(chatId: number, specialistId: number): Promise<BackendChat> {
  const body: AssignRequest = { specialist_id: specialistId };
  const res = await fetch(`${API_BASE}/specialist/chats/${chatId}/assign`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  return handleResponse<BackendChat>(res);
}

export async function reviewChat(
  chatId: number,
  action: 'approve' | 'reject',
  feedback?: string,
): Promise<BackendChat> {
  const body: ReviewRequest = { action, feedback };
  const res = await fetch(`${API_BASE}/specialist/chats/${chatId}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  return handleResponse<BackendChat>(res);
}

// ── Health ────────────────────────────────────────────────────────────────

export async function healthCheck(): Promise<{ status: string; system: string }> {
  const res = await fetch(`${API_BASE}/health`);
  return handleResponse<{ status: string; system: string }>(res);
}

// ── Specialist messaging ─────────────────────────────────────────────────

export async function sendSpecialistMessage(
  chatId: number,
  content: string,
): Promise<{ status: string; message_id: number }> {
  const res = await fetch(`${API_BASE}/specialist/chats/${chatId}/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ content }),
  });
  return handleResponse<{ status: string; message_id: number }>(res);
}

// ── Notifications ────────────────────────────────────────────────────────

export async function getNotifications(
  unreadOnly = false,
): Promise<NotificationResponse[]> {
  const params = new URLSearchParams();
  if (unreadOnly) params.set('unread_only', 'true');
  const res = await fetch(`${API_BASE}/notifications/?${params}`, {
    headers: authHeaders(),
  });
  return handleResponse<NotificationResponse[]>(res);
}

export async function markNotificationRead(
  notificationId: number,
): Promise<NotificationResponse> {
  const res = await fetch(`${API_BASE}/notifications/${notificationId}/read`, {
    method: 'PATCH',
    headers: authHeaders(),
  });
  return handleResponse<NotificationResponse>(res);
}

export async function markAllNotificationsRead(): Promise<{ marked_read: number }> {
  const res = await fetch(`${API_BASE}/notifications/read-all`, {
    method: 'PATCH',
    headers: authHeaders(),
  });
  return handleResponse<{ marked_read: number }>(res);
}

// ── Admin: Users ─────────────────────────────────────────────────────────

export async function adminGetUsers(role?: string): Promise<UserProfile[]> {
  const params = new URLSearchParams();
  if (role) params.set('role', role);
  const res = await fetch(`${API_BASE}/admin/users?${params}`, {
    headers: authHeaders(),
  });
  return handleResponse<UserProfile[]>(res);
}

export async function adminGetUser(userId: number): Promise<UserProfile> {
  const res = await fetch(`${API_BASE}/admin/users/${userId}`, {
    headers: authHeaders(),
  });
  return handleResponse<UserProfile>(res);
}

export async function adminUpdateUser(
  userId: number,
  payload: UserUpdateAdmin,
): Promise<UserProfile> {
  const res = await fetch(`${API_BASE}/admin/users/${userId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(payload),
  });
  return handleResponse<UserProfile>(res);
}

export async function adminDeactivateUser(userId: number): Promise<UserProfile> {
  const res = await fetch(`${API_BASE}/admin/users/${userId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  return handleResponse<UserProfile>(res);
}

// ── Admin: Chats ─────────────────────────────────────────────────────────

export async function adminGetChats(filters?: {
  status?: string;
  specialty?: string;
  user_id?: number;
  specialist_id?: number;
  skip?: number;
  limit?: number;
}): Promise<AdminChatResponse[]> {
  const params = new URLSearchParams();
  if (filters?.status) params.set('status', filters.status);
  if (filters?.specialty) params.set('specialty', filters.specialty);
  if (filters?.user_id) params.set('user_id', String(filters.user_id));
  if (filters?.specialist_id) params.set('specialist_id', String(filters.specialist_id));
  if (filters?.skip) params.set('skip', String(filters.skip));
  if (filters?.limit) params.set('limit', String(filters.limit));
  const res = await fetch(`${API_BASE}/admin/chats?${params}`, {
    headers: authHeaders(),
  });
  return handleResponse<AdminChatResponse[]>(res);
}

export async function adminGetChat(chatId: number): Promise<BackendChatWithMessages> {
  const res = await fetch(`${API_BASE}/admin/chats/${chatId}`, {
    headers: authHeaders(),
  });
  return handleResponse<BackendChatWithMessages>(res);
}

export async function adminUpdateChat(
  chatId: number,
  payload: ChatUpdateRequest,
): Promise<AdminChatResponse> {
  const res = await fetch(`${API_BASE}/admin/chats/${chatId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(payload),
  });
  return handleResponse<AdminChatResponse>(res);
}

export async function adminDeleteChat(chatId: number): Promise<void> {
  const res = await fetch(`${API_BASE}/admin/chats/${chatId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  return handleResponse<void>(res);
}

// ── Admin: Audit Logs ────────────────────────────────────────────────────

export async function adminGetLogs(filters?: {
  action?: string;
  category?: string;
  search?: string;
  user_id?: number;
  date_from?: string;
  date_to?: string;
  limit?: number;
}): Promise<AuditLogResponse[]> {
  const params = new URLSearchParams();
  if (filters?.action) params.set('action', filters.action);
  if (filters?.category) params.set('category', filters.category);
  if (filters?.search) params.set('search', filters.search);
  if (filters?.user_id) params.set('user_id', String(filters.user_id));
  if (filters?.date_from) params.set('date_from', filters.date_from);
  if (filters?.date_to) params.set('date_to', filters.date_to);
  if (filters?.limit) params.set('limit', String(filters.limit));
  const res = await fetch(`${API_BASE}/admin/logs?${params}`, {
    headers: authHeaders(),
  });
  return handleResponse<AuditLogResponse[]>(res);
}
