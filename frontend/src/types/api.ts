// Types matching the backend API responses

export interface BackendMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export interface BackendChat {
  id: number;
  title: string | null;
  user_id: number;
  created_at: string;
  messages: BackendMessage[];
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: {
    email: string;
    full_name: string | null;
    role: 'gp' | 'specialist' | 'admin';
  };
}

export interface RegisterRequest {
  first_name: string;
  last_name: string;
  email: string;
  password: string;
  role: 'gp' | 'specialist' | 'admin';
  specialty?: string;
}

export interface ChatCreateRequest {
  title?: string;
}

export interface MessageCreateRequest {
  role: string;
  content: string;
}
