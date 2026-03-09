// Types matching the backend API responses

// ---------------------------------------------------------------------------
// Messages
// ---------------------------------------------------------------------------

export interface BackendMessage {
  id: number;
  content: string;
  sender: string;          // "user" | "ai" | "specialist"
  created_at: string;
  citations?: unknown[] | null;
  citations_used?: unknown[] | null;
  citations_retrieved?: unknown[] | null;
  is_generating?: boolean;
  review_status?: string | null;
  review_feedback?: string | null;
  reviewed_at?: string | null;
}

// ---------------------------------------------------------------------------
// Chat (list endpoints — no messages)
// ---------------------------------------------------------------------------

export interface BackendChat {
  id: number;
  title: string;
  status: string;            // ChatStatus enum on backend
  specialty: string | null;
  severity: string | null;
  patient_age?: number | null;
  patient_gender?: string | null;
  patient_notes?: string | null;
  specialist_id: number | null;
  assigned_at: string | null;
  reviewed_at: string | null;
  review_feedback: string | null;
  created_at: string;
  user_id: number;
}

// ---------------------------------------------------------------------------
// Chat with messages (detail endpoints)
// ---------------------------------------------------------------------------

export interface BackendChatWithMessages extends BackendChat {
  messages: BackendMessage[];
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export interface UserProfile {
  id: number;
  email: string;
  full_name: string | null;
  role: 'gp' | 'specialist' | 'admin';
  specialty: string | null;
  is_active: boolean;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: UserProfile;
}

export interface RegisterRequest {
  email: string;
  password: string;
  full_name?: string;
  role: 'gp' | 'specialist' | 'admin';
  specialty?: string;
}

export interface ProfileUpdateRequest {
  full_name?: string | null;
  specialty?: string | null;
  current_password?: string | null;
  new_password?: string | null;
}

// ---------------------------------------------------------------------------
// Chat create / message create
// ---------------------------------------------------------------------------

export interface ChatCreateRequest {
  title?: string;
  specialty?: string;
  severity?: string;
  patient_age?: number;
  patient_gender?: string;
  patient_notes?: string;
}

export interface MessageCreateRequest {
  role: string;
  content: string;
}

export interface GPMessageResponse {
  status: string;
  ai_response: string;
  ai_generating?: boolean;
}

// ---------------------------------------------------------------------------
// Specialist workflow
// ---------------------------------------------------------------------------

export interface AssignRequest {
  specialist_id: number;
}

export interface ReviewRequest {
  action: 'approve' | 'reject' | 'request_changes' | 'manual_response';
  feedback?: string | null;
  replacement_content?: string | null;
}

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------

export interface NotificationResponse {
  id: number;
  type: string;       // "chat_assigned" | "specialist_msg" | "chat_approved" | "chat_rejected"
  title: string;
  body: string | null;
  chat_id: number | null;
  is_read: boolean;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Admin
// ---------------------------------------------------------------------------

export interface UserUpdateAdmin {
  full_name?: string | null;
  specialty?: string | null;
  role?: string | null;
  is_active?: boolean | null;
}

export interface AdminChatResponse {
  id: number;
  title: string;
  status: string;
  specialty: string | null;
  severity: string | null;
  user_id: number;
  owner_identifier: string | null;
  specialist_id: number | null;
  specialist_identifier: string | null;
  assigned_at: string | null;
  reviewed_at: string | null;
  review_feedback: string | null;
  created_at: string;
}

export interface AuditLogResponse {
  id: number;
  user_id: number | null;
  user_identifier: string | null;
  action: string;
  category: string;   // "AUTH" | "CHAT" | "SPECIALIST" | "RAG" | "OTHER"
  details: string | null;
  timestamp: string;
}

export interface ChatUpdateRequest {
  title?: string | null;
  status?: string | null;
  specialty?: string | null;
  severity?: string | null;
}

export interface DailyCount {
  date: string;
  count: number;
}

export interface AdminStatsResponse {
  total_ai_responses: number;
  rag_grounded_responses: number;
  specialist_responses: number;
  active_consultations: number;
  chats_by_status: Record<string, number>;
  chats_by_specialty: Record<string, number>;
  active_users_by_role: Record<string, number>;
  daily_ai_queries: DailyCount[];
}
