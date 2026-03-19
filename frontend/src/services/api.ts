import type {
  BackendChat,
  BackendChatWithMessages,
  FileAttachment,
  GPMessageResponse,
  LoginResponse,
  RegisterResponse,
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
  AdminStatsResponse,
  VerificationStatusResponse,
} from '../types/api';
import { setOptionalSearchParam } from '../utils/url';

type ApiRequestInit = RequestInit & { skipAuthRefresh?: boolean };
export interface RequestOptions {
  signal?: AbortSignal;
}
let refreshInFlight: Promise<boolean> | null = null;

function apiUrl(path: string): string {
  const base = import.meta.env.VITE_API_URL || '';
  return `${base}${path}`;
}

function redirectToLogin(): void {
  window.history.replaceState(null, '', '/login');
  window.dispatchEvent(new PopStateEvent('popstate'));
}

function clearStoredSession(): void {
  localStorage.removeItem('access_token');
  localStorage.removeItem('username');
  localStorage.removeItem('user_role');
  localStorage.removeItem('user_email');
}

function authHeaders(): Record<string, string> {
  return {};
}

async function refreshSessionRequest(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      const res = await globalThis.fetch(apiUrl('/auth/refresh'), {
        method: 'POST',
        credentials: 'include',
      });
      return res.ok;
    })().finally(() => {
      refreshInFlight = null;
    });
  }

  return refreshInFlight;
}

async function apiFetch(input: RequestInfo | URL, init: ApiRequestInit = {}): Promise<Response> {
  const { skipAuthRefresh = false, ...requestInit } = init;

  const doFetch = () =>
    globalThis.fetch(input, {
      credentials: 'include',
      ...requestInit,
    });

  let res = await doFetch();
  if (res.status === 401 && !skipAuthRefresh) {
    const refreshed = await refreshSessionRequest();
    if (refreshed) {
      res = await doFetch();
    }
  }

  return res;
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (res.status === 401) {
    clearStoredSession();
    redirectToLogin();
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
  if (res.status === 204) return undefined as unknown as T;
  return res.json();
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const body = new URLSearchParams();
  body.append('username', username);
  body.append('password', password);

  const res = await apiFetch(apiUrl('/auth/login'), {
    method: 'POST',
    skipAuthRefresh: true,
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });

  return handleResponse<LoginResponse>(res);
}

export async function register(payload: RegisterRequest): Promise<RegisterResponse> {
  const res = await apiFetch(apiUrl('/auth/register'), {
    method: 'POST',
    skipAuthRefresh: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  return handleResponse<RegisterResponse>(res);
}

export async function forgotPassword(email: string): Promise<{ message: string }> {
  const res = await apiFetch(apiUrl('/auth/forgot-password'), {
    method: 'POST',
    skipAuthRefresh: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });
  return handleResponse<{ message: string }>(res);
}

export async function resetPasswordConfirm(
  token: string,
  newPassword: string,
): Promise<{ message: string }> {
  const res = await apiFetch(apiUrl('/auth/reset-password/confirm'), {
    method: 'POST',
    skipAuthRefresh: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, new_password: newPassword }),
  });
  return handleResponse<{ message: string }>(res);
}

export async function resendVerificationEmail(email: string): Promise<{ message: string }> {
  const res = await apiFetch(apiUrl('/auth/resend-verification'), {
    method: 'POST',
    skipAuthRefresh: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  });
  return handleResponse<{ message: string }>(res);
}

export async function confirmEmailVerification(token: string): Promise<{ message: string }> {
  const res = await apiFetch(apiUrl('/auth/verify-email/confirm'), {
    method: 'POST',
    skipAuthRefresh: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token }),
  });
  return handleResponse<{ message: string }>(res);
}

export async function getVerificationStatus(
  options: RequestOptions = {},
): Promise<VerificationStatusResponse> {
  const res = await apiFetch(apiUrl('/auth/verification-status'), {
    signal: options.signal,
    headers: authHeaders(),
  });
  return handleResponse<VerificationStatusResponse>(res);
}

export async function logout(): Promise<{ message?: string; success?: boolean }> {
  const res = await apiFetch(apiUrl('/auth/logout'), {
    method: 'POST',
    skipAuthRefresh: true,
    headers: authHeaders(),
  });
  return handleResponse<{ message?: string; success?: boolean }>(res);
}

export async function refreshSession(options: RequestOptions = {}): Promise<LoginResponse> {
  const res = await apiFetch(apiUrl('/auth/refresh'), {
    method: 'POST',
    skipAuthRefresh: true,
    signal: options.signal,
  });
  return handleResponse<LoginResponse>(res);
}

export async function getProfile(options: RequestOptions = {}): Promise<UserProfile> {
  const res = await apiFetch(apiUrl('/auth/me'), {
    signal: options.signal,
    headers: authHeaders(),
  });
  return handleResponse<UserProfile>(res);
}

export async function updateProfile(data: ProfileUpdateRequest): Promise<UserProfile> {
  const res = await apiFetch(apiUrl('/auth/profile'), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(data),
  });
  return handleResponse<UserProfile>(res);
}

export interface ChatListFilters {
  skip?: number;
  limit?: number;
  status?: string;
  specialty?: string;
  search?: string;
  date_from?: string;
  date_to?: string;
}

export async function getChats(
  filters: ChatListFilters = {},
  options: RequestOptions = {},
): Promise<BackendChat[]> {
  const params = new URLSearchParams();
  params.set('skip', String(filters.skip ?? 0));
  params.set('limit', String(filters.limit ?? 100));
  if (filters.status) params.set('status', filters.status);
  if (filters.specialty) params.set('specialty', filters.specialty);
  if (filters.search) params.set('search', filters.search);
  if (filters.date_from) params.set('date_from', filters.date_from);
  if (filters.date_to) params.set('date_to', filters.date_to);
  const res = await apiFetch(apiUrl(`/chats/?${params}`), {
    signal: options.signal,
    headers: authHeaders(),
  });
  return handleResponse<BackendChat[]>(res);
}

export async function getChat(
  chatId: number,
  options: RequestOptions = {},
): Promise<BackendChatWithMessages> {
  const res = await apiFetch(apiUrl(`/chats/${chatId}`), {
    signal: options.signal,
    headers: authHeaders(),
  });
  return handleResponse<BackendChatWithMessages>(res);
}

export async function createChat(data: ChatCreateRequest): Promise<BackendChat> {
  const res = await apiFetch(apiUrl('/chats/'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(data),
  });
  return handleResponse<BackendChat>(res);
}

export async function uploadChatFile(chatId: number, file: File): Promise<FileAttachment> {
  const formData = new FormData();
  formData.append('file', file);
  const res = await apiFetch(apiUrl(`/chats/${chatId}/files`), {
    method: 'POST',
    headers: authHeaders(),
    body: formData,
  });
  return handleResponse<FileAttachment>(res);
}

export async function deleteChat(chatId: number): Promise<void> {
  const res = await apiFetch(apiUrl(`/chats/${chatId}`), {
    method: 'DELETE',
    headers: authHeaders(),
  });
  return handleResponse<void>(res);
}

export async function updateChat(
  chatId: number,
  payload: ChatUpdateRequest,
): Promise<BackendChat> {
  const res = await apiFetch(apiUrl(`/chats/${chatId}`), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(payload),
  });
  return handleResponse<BackendChat>(res);
}

export async function submitForReview(chatId: number): Promise<BackendChat> {
  const res = await apiFetch(apiUrl(`/chats/${chatId}/submit`), {
    method: 'POST',
    headers: authHeaders(),
  });
  return handleResponse<BackendChat>(res);
}

export async function sendMessage(
  chatId: number,
  content: string,
): Promise<GPMessageResponse> {
  const body: MessageCreateRequest = { role: 'user', content };
  const res = await apiFetch(apiUrl(`/chats/${chatId}/message`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  return handleResponse<GPMessageResponse>(res);
}

export async function getSpecialistQueue(): Promise<BackendChat[]> {
  const res = await apiFetch(apiUrl('/specialist/queue'), {
    headers: authHeaders(),
  });
  return handleResponse<BackendChat[]>(res);
}

export async function getAssignedChats(): Promise<BackendChat[]> {
  const res = await apiFetch(apiUrl('/specialist/assigned'), {
    headers: authHeaders(),
  });
  return handleResponse<BackendChat[]>(res);
}

export async function getSpecialistChatDetail(
  chatId: number,
  options: RequestOptions = {},
): Promise<BackendChatWithMessages> {
  const res = await apiFetch(apiUrl(`/specialist/chats/${chatId}`), {
    signal: options.signal,
    headers: authHeaders(),
  });
  return handleResponse<BackendChatWithMessages>(res);
}

export async function assignChat(chatId: number, specialistId: number): Promise<BackendChat> {
  const body: AssignRequest = { specialist_id: specialistId };
  const res = await apiFetch(apiUrl(`/specialist/chats/${chatId}/assign`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  return handleResponse<BackendChat>(res);
}

export async function reviewChat(
  chatId: number,
  decision: string,
): Promise<BackendChat> {
  const body: ReviewRequest = { decision };
  const res = await apiFetch(apiUrl(`/specialist/chats/${chatId}/review`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  return handleResponse<BackendChat>(res);
}

export async function reviewMessage(
  chatId: number,
  messageId: number,
  decision: string,
  feedback?: string,
  manualContent?: string,
  manualSources?: string[],
): Promise<BackendChat> {
  const body: ReviewRequest = { decision, feedback, manual_content: manualContent, manual_sources: manualSources };
  const res = await apiFetch(apiUrl(`/specialist/chats/${chatId}/messages/${messageId}/review`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  return handleResponse<BackendChat>(res);
}

export async function sendSpecialistMessage(
  chatId: number,
  content: string,
): Promise<{ status: string; message_id: number }> {
  const body: MessageCreateRequest = { role: 'specialist', content };
  const res = await apiFetch(apiUrl(`/specialist/chats/${chatId}/message`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  return handleResponse<{ status: string; message_id: number }>(res);
}

export async function getNotifications(): Promise<NotificationResponse[]> {
  const res = await apiFetch(apiUrl('/notifications/'), {
    headers: authHeaders(),
  });
  return handleResponse<NotificationResponse[]>(res);
}

export async function markNotificationRead(notificationId: number): Promise<void> {
  const res = await apiFetch(apiUrl(`/notifications/${notificationId}/read`), {
    method: 'POST',
    headers: authHeaders(),
  });
  return handleResponse<void>(res);
}

export async function markAllNotificationsRead(): Promise<void> {
  const res = await apiFetch(apiUrl('/notifications/read-all'), {
    method: 'POST',
    headers: authHeaders(),
  });
  return handleResponse<void>(res);
}

export async function adminGetUsers(params: {
  role?: string;
  specialty?: string;
  active_only?: boolean;
  search?: string;
} = {}): Promise<UserProfile[]> {
  const query = new URLSearchParams();
  setOptionalSearchParam(query, 'role', params.role);
  setOptionalSearchParam(query, 'specialty', params.specialty);
  if (params.active_only != null) query.set('active_only', String(params.active_only));
  setOptionalSearchParam(query, 'search', params.search);
  const suffix = query.toString() ? `?${query}` : '';
  const res = await apiFetch(apiUrl(`/admin/users${suffix}`), {
    headers: authHeaders(),
  });
  return handleResponse<UserProfile[]>(res);
}

export async function adminGetUser(userId: number): Promise<UserProfile> {
  const res = await apiFetch(apiUrl(`/admin/users/${userId}`), {
    headers: authHeaders(),
  });
  return handleResponse<UserProfile>(res);
}

export async function adminUpdateUser(userId: number, payload: UserUpdateAdmin): Promise<UserProfile> {
  const res = await apiFetch(apiUrl(`/admin/users/${userId}`), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(payload),
  });
  return handleResponse<UserProfile>(res);
}

export async function adminDeactivateUser(userId: number): Promise<void> {
  const res = await apiFetch(apiUrl(`/admin/users/${userId}`), {
    method: 'DELETE',
    headers: authHeaders(),
  });
  return handleResponse<void>(res);
}

export async function adminGetChats(params: {
  status?: string;
  specialty?: string;
  owner_q?: string;
} = {}): Promise<AdminChatResponse[]> {
  const query = new URLSearchParams();
  setOptionalSearchParam(query, 'status', params.status);
  setOptionalSearchParam(query, 'specialty', params.specialty);
  setOptionalSearchParam(query, 'owner_q', params.owner_q);
  const suffix = query.toString() ? `?${query}` : '';
  const res = await apiFetch(apiUrl(`/admin/chats${suffix}`), {
    headers: authHeaders(),
  });
  return handleResponse<AdminChatResponse[]>(res);
}

export async function adminGetChat(chatId: number): Promise<AdminChatResponse> {
  const res = await apiFetch(apiUrl(`/admin/chats/${chatId}`), {
    headers: authHeaders(),
  });
  return handleResponse<AdminChatResponse>(res);
}

export async function adminUpdateChat(chatId: number, payload: ChatUpdateRequest): Promise<AdminChatResponse> {
  const res = await apiFetch(apiUrl(`/admin/chats/${chatId}`), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(payload),
  });
  return handleResponse<AdminChatResponse>(res);
}

export async function adminDeleteChat(chatId: number): Promise<void> {
  const res = await apiFetch(apiUrl(`/admin/chats/${chatId}`), {
    method: 'DELETE',
    headers: authHeaders(),
  });
  return handleResponse<void>(res);
}

export async function adminGetStats(): Promise<AdminStatsResponse> {
  const res = await apiFetch(apiUrl('/admin/stats'), {
    headers: authHeaders(),
  });
  return handleResponse<AdminStatsResponse>(res);
}

export async function adminGetLogs(params: {
  action?: string;
  category?: string;
  search?: string;
  user_id?: number;
} = {}): Promise<AuditLogResponse[]> {
  const query = new URLSearchParams();
  setOptionalSearchParam(query, 'action', params.action);
  setOptionalSearchParam(query, 'category', params.category);
  setOptionalSearchParam(query, 'search', params.search);
  if (params.user_id != null) query.set('user_id', String(params.user_id));
  const suffix = query.toString() ? `?${query}` : '';
  const res = await apiFetch(apiUrl(`/admin/logs${suffix}`), {
    headers: authHeaders(),
  });
  return handleResponse<AuditLogResponse[]>(res);
}

export interface IngestionReport {
  source_name: string;
  filename: string;
  files_scanned: number;
  files_succeeded: number;
  files_failed: number;
  total_chunks: number;
  embeddings_succeeded: number;
  embeddings_failed: number;
  db: {
    inserted: number;
    updated: number;
    skipped: number;
    failed: number;
  };
}

export async function adminUploadGuideline(file: File, sourceName: string): Promise<IngestionReport> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('source_name', sourceName);
  const res = await apiFetch(apiUrl('/admin/guidelines/upload'), {
    method: 'POST',
    headers: authHeaders(),
    body: formData,
  });
  return handleResponse<IngestionReport>(res);
}

export async function healthCheck(): Promise<{ status: string }> {
  const res = await apiFetch(apiUrl('/health'), {
    skipAuthRefresh: true,
  });
  return handleResponse<{ status: string }>(res);
}

export function subscribeToChatStream(
  chatId: number,
  token: string,
  handlers: {
    onStreamStart?: (data: { chat_id: number; message_id: number }) => void;
    onContent?: (data: { chat_id: number; message_id: number; content: string }) => void;
    onComplete?: (data: { chat_id: number; message_id: number; content: string; citations?: unknown[] }) => void;
    onError?: (data: { error: string }) => void;
  },
): () => void {
  const base = import.meta.env.VITE_API_URL || '';
  const source = new EventSource(`${base}/chats/${chatId}/stream?token=${encodeURIComponent(token)}`);

  source.addEventListener('stream_start', (event) => {
    handlers.onStreamStart?.(JSON.parse(event.data));
  });
  source.addEventListener('content', (event) => {
    handlers.onContent?.(JSON.parse(event.data));
  });
  source.addEventListener('complete', (event) => {
    handlers.onComplete?.(JSON.parse(event.data));
  });
  source.addEventListener('error', (event) => {
    handlers.onError?.(JSON.parse(event.data));
  });

  source.onerror = () => {
    source.close();
  };

  return () => source.close();
}
