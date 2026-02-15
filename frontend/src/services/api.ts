import type {
  BackendChat,
  BackendMessage,
  LoginResponse,
  ChatCreateRequest,
  MessageCreateRequest,
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

// ── Chats ────────────────────────────────────────────────────────────────

export async function getChats(skip = 0, limit = 100): Promise<BackendChat[]> {
  const params = new URLSearchParams({ skip: String(skip), limit: String(limit) });
  const res = await fetch(`${API_BASE}/chats/?${params}`, {
    headers: authHeaders(),
  });
  return handleResponse<BackendChat[]>(res);
}

export async function getChat(chatId: number): Promise<BackendChat> {
  const res = await fetch(`${API_BASE}/chats/${chatId}`, {
    headers: authHeaders(),
  });
  return handleResponse<BackendChat>(res);
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

// ── Health ────────────────────────────────────────────────────────────────

export async function healthCheck(): Promise<{ status: string; system: string }> {
  const res = await fetch(`${API_BASE}/health`);
  return handleResponse<{ status: string; system: string }>(res);
}
