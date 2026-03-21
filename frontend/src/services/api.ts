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
  RagStatusResponse,
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
  const token = localStorage.getItem('access_token');
  if (!token) return {};
  return { Authorization: `Bearer ${token}` };
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
  const body: MessageCreateRequest = { content };
  const res = await apiFetch(apiUrl(`/chats/${chatId}/message`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  return handleResponse<GPMessageResponse>(res);
}

export async function getSpecialistQueue(options: RequestOptions = {}): Promise<BackendChat[]> {
  const res = await apiFetch(apiUrl('/specialist/queue'), {
    signal: options.signal,
    headers: authHeaders(),
  });
  return handleResponse<BackendChat[]>(res);
}

export async function getAssignedChats(options: RequestOptions = {}): Promise<BackendChat[]> {
  const res = await apiFetch(apiUrl('/specialist/assigned'), {
    signal: options.signal,
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
  feedback?: string,
): Promise<BackendChat> {
  const body: ReviewRequest = {
    action: decision as ReviewRequest['action'],
    feedback: feedback ?? null,
  };
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
  editedContent?: string,
): Promise<BackendChat> {
  const body: ReviewRequest = {
    action: decision as ReviewRequest['action'],
    feedback: feedback ?? null,
    replacement_content: manualContent ?? null,
    replacement_sources: manualSources ?? null,
    edited_content: editedContent ?? null,
  };
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
  const body: MessageCreateRequest = { content };
  const res = await apiFetch(apiUrl(`/specialist/chats/${chatId}/message`), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  return handleResponse<{ status: string; message_id: number }>(res);
}

export async function getNotifications(unreadOnly = false): Promise<NotificationResponse[]> {
  const query = unreadOnly ? '?unread_only=true' : '';
  const res = await apiFetch(apiUrl(`/notifications/${query}`), {
    headers: authHeaders(),
  });
  return handleResponse<NotificationResponse[]>(res);
}

export async function markNotificationRead(
  notificationId: number,
): Promise<{ is_read: boolean }> {
  const res = await apiFetch(apiUrl(`/notifications/${notificationId}/read`), {
    method: 'PATCH',
    headers: authHeaders(),
  });
  const payload = await handleResponse<NotificationResponse | undefined>(res);
  return { is_read: payload?.is_read ?? true };
}

export async function markAllNotificationsRead(): Promise<{ marked_read: number }> {
  const res = await apiFetch(apiUrl('/notifications/read-all'), {
    method: 'PATCH',
    headers: authHeaders(),
  });
  const payload = await handleResponse<{ marked_read?: number } | undefined>(res);
  return { marked_read: payload?.marked_read ?? 0 };
}

type AdminUserFilters = {
  role?: string;
  specialty?: string;
  active_only?: boolean;
  search?: string;
};

export async function adminGetUsers(
  roleOrParams: string | AdminUserFilters = {},
  options: RequestOptions = {},
): Promise<UserProfile[]> {
  const params: AdminUserFilters =
    typeof roleOrParams === 'string' ? { role: roleOrParams } : roleOrParams;
  const query = new URLSearchParams();
  setOptionalSearchParam(query, 'role', params.role);
  setOptionalSearchParam(query, 'specialty', params.specialty);
  if (params.active_only != null) query.set('active_only', String(params.active_only));
  setOptionalSearchParam(query, 'search', params.search);
  const suffix = query.toString() ? `?${query}` : '';
  const res = await apiFetch(apiUrl(`/admin/users${suffix}`), {
    signal: options.signal,
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

export async function adminDeactivateUser(userId: number): Promise<UserProfile> {
  const res = await apiFetch(apiUrl(`/admin/users/${userId}`), {
    method: 'DELETE',
    headers: authHeaders(),
  });
  const payload = await handleResponse<UserProfile | undefined>(res);
  return payload ?? ({ id: userId, is_active: false } as UserProfile);
}

export async function adminGetChats(params: {
  status?: string;
  specialty?: string;
  owner_q?: string;
  user_id?: number;
  specialist_id?: number;
  skip?: number;
  limit?: number;
} = {}, options: RequestOptions = {}): Promise<AdminChatResponse[]> {
  const query = new URLSearchParams();
  setOptionalSearchParam(query, 'status', params.status);
  setOptionalSearchParam(query, 'specialty', params.specialty);
  setOptionalSearchParam(query, 'owner_q', params.owner_q);
  if (params.user_id != null) query.set('user_id', String(params.user_id));
  if (params.specialist_id != null) {
    query.set('specialist_id', String(params.specialist_id));
  }
  if (params.skip != null) query.set('skip', String(params.skip));
  if (params.limit != null) query.set('limit', String(params.limit));
  const suffix = query.toString() ? `?${query}` : '';
  const res = await apiFetch(apiUrl(`/admin/chats${suffix}`), {
    signal: options.signal,
    headers: authHeaders(),
  });
  return handleResponse<AdminChatResponse[]>(res);
}

export async function adminGetChat(
  chatId: number,
  options: RequestOptions = {},
): Promise<BackendChatWithMessages> {
  const res = await apiFetch(apiUrl(`/admin/chats/${chatId}`), {
    signal: options.signal,
    headers: authHeaders(),
  });
  const payload = await handleResponse<Partial<BackendChatWithMessages>>(res);
  return {
    ...(payload as BackendChatWithMessages),
    messages: Array.isArray(payload.messages) ? payload.messages : [],
  };
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

export async function adminGetStats(options: RequestOptions = {}): Promise<AdminStatsResponse> {
  const res = await apiFetch(apiUrl('/admin/stats'), {
    signal: options.signal,
    headers: authHeaders(),
  });
  return handleResponse<AdminStatsResponse>(res);
}

export async function adminGetLogs(params: {
  action?: string;
  category?: string;
  search?: string;
  user_id?: number;
  date_from?: string;
  date_to?: string;
  limit?: number;
} = {}, options: RequestOptions = {}): Promise<AuditLogResponse[]> {
  const query = new URLSearchParams();
  setOptionalSearchParam(query, 'action', params.action);
  setOptionalSearchParam(query, 'category', params.category);
  setOptionalSearchParam(query, 'search', params.search);
  if (params.user_id != null) query.set('user_id', String(params.user_id));
  setOptionalSearchParam(query, 'date_from', params.date_from);
  setOptionalSearchParam(query, 'date_to', params.date_to);
  if (params.limit != null) query.set('limit', String(params.limit));
  const suffix = query.toString() ? `?${query}` : '';
  const res = await apiFetch(apiUrl(`/admin/logs${suffix}`), {
    signal: options.signal,
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

export async function adminGetRagStatus(options: RequestOptions = {}): Promise<RagStatusResponse> {
  const res = await apiFetch(apiUrl('/admin/rag/status'), {
    signal: options.signal,
    headers: authHeaders(),
  });
  return handleResponse<RagStatusResponse>(res);
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

export async function healthCheck(): Promise<{ status: string; system?: string }> {
  const res = await apiFetch(apiUrl('/health'), {
    skipAuthRefresh: true,
  });
  const payload = await handleResponse<{ status: string; system?: string }>(res);
  if (payload.status === 'healthy') {
    return { status: 'ok', system: payload.system ?? 'healthy' };
  }
  return payload;
}

export function subscribeToChatStream(
  chatId: number,
  handlers: {
    onOpen?: () => void;
    onStreamStart?: (messageId: number) => void;
    onContent?: (messageId: number, content: string) => void;
    onComplete?: (messageId: number, content: string, citations: unknown[] | null) => void;
    onFileContextTruncated?: () => void;
    onError?: (messageId: number, errorMessage: string) => void;
    onConnectionError?: () => void;
  },
): () => void {
  const base = import.meta.env.VITE_API_URL || '';
  const streamUrl = `${base}/chats/${chatId}/stream`;
  const source = new EventSource(streamUrl, { withCredentials: true });
  let closed = false;
  let handledError = false;

  const closeSource = () => {
    if (closed) return;
    closed = true;
    source.close();
  };

  source.onopen = () => {
    if (closed) return;
    handlers.onOpen?.();
  };

  const parsePayload = <T,>(event: MessageEvent<string>): T | null => {
    try {
      return JSON.parse(event.data) as T;
    } catch {
      return null;
    }
  };

  source.addEventListener('stream_start', (event) => {
    if (closed) return;
    const payload = parsePayload<{ message_id?: number }>(event as MessageEvent<string>);
    if (typeof payload?.message_id === 'number') {
      handlers.onStreamStart?.(payload.message_id);
    }
  });

  source.addEventListener('content', (event) => {
    if (closed) return;
    const payload = parsePayload<{ message_id?: number; content?: string }>(
      event as MessageEvent<string>,
    );
    if (typeof payload?.message_id === 'number') {
      handlers.onContent?.(payload.message_id, payload.content ?? '');
    }
  });

  source.addEventListener('complete', (event) => {
    if (closed) return;
    const payload = parsePayload<{
      message_id?: number;
      content?: string;
      citations?: unknown[];
      file_context_truncated?: boolean;
    }>(event as MessageEvent<string>);
    if (typeof payload?.message_id === 'number') {
      if (payload.file_context_truncated === true) {
        handlers.onFileContextTruncated?.();
      }
      handlers.onComplete?.(
        payload.message_id,
        payload.content ?? '',
        payload.citations ?? null,
      );
      closeSource();
    }
  });

  source.addEventListener('error', (event) => {
    if (handledError || closed) return;
    handledError = true;
    const payload = parsePayload<{ message_id?: number; error?: string }>(
      event as MessageEvent<string>,
    );
    handlers.onError?.(payload?.message_id ?? chatId, payload?.error ?? 'Unknown error');
    closeSource();
  });

  source.onerror = () => {
    if (handledError || closed) return;
    handledError = true;
    handlers.onConnectionError?.();
    closeSource();
  };

  return closeSource;
}
