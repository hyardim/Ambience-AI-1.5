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
