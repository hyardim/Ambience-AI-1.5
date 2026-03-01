export type UserRole = 'gp' | 'specialist' | 'admin';

export type QueryStatus = 'active' | 'resolved' | 'pending-review';

export type Severity = 'low' | 'medium' | 'high' | 'urgent';

export type Specialty = 'neurology' | 'rheumatology';

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
  avatar?: string;
}

export interface FileAttachment {
  id: string;
  name: string;
  size: string;
  type: string;
}

export interface GuidelineReference {
  title: string;
  referenceNo: string;
  lastUpdated: string;
}

export interface Message {
  id: string;
  senderId: string;
  senderName: string;
  senderType: 'gp' | 'specialist' | 'ai';
  content: string;
  timestamp: Date;
  attachments?: FileAttachment[];
  guidelineReference?: GuidelineReference;
  reviewStatus?: string | null;       // null | "approved" | "rejected"
  reviewFeedback?: string | null;
  reviewedAt?: string | null;
}

export interface Query {
  id: string;
  title: string;
  description: string;
  specialty: Specialty;
  severity: Severity;
  status: QueryStatus;
  createdAt: Date;
  updatedAt: Date;
  gpId: string;
  gpName: string;
  messages: Message[];
  attachments?: FileAttachment[];
  aiResponsePending?: boolean;
  specialistReviewRequired?: boolean;
}

export interface Notification {
  id: string;
  queryId: string;
  queryTitle: string;
  message: string;
  senderName: string;
  senderType: 'specialist' | 'ai';
  read: boolean;
  timestamp: Date;
}
