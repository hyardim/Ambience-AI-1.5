import type { BackendMessage } from '../types/api';
import type { Message, Citation } from '../types';

/** Safely map raw citation objects coming from the backend to the frontend Citation shape. */
export function mapCitations(raw?: unknown[] | null, fallback?: unknown[] | null): Citation[] {
  const list = Array.isArray(raw) && raw.length > 0
    ? raw
    : Array.isArray(fallback)
      ? fallback
      : [];

  return list
    .map((c: any) => {
      if (!c || typeof c !== 'object') return null;
      const meta = (c as any).metadata || {};
      const docId = (c as any).doc_id ?? meta.doc_id;
      const sectionPath = (c as any).section_path ?? meta.section_path;
      const pageStart = (c as any).page_start ?? meta.page_start;
      const pageEnd = (c as any).page_end ?? meta.page_end;

      return {
        doc_id: docId || undefined,
        title: meta.title || meta.filename || (c as any).source || 'Source',
        source_name: meta.source_name || (c as any).source || 'Source',
        specialty: meta.specialty,
        section_path: sectionPath,
        page_start: typeof pageStart === 'number' ? pageStart : undefined,
        page_end: typeof pageEnd === 'number' ? pageEnd : undefined,
        source_url: meta.source_url,
      } satisfies Citation;
    })
    .filter(Boolean) as Citation[];
}

/** Map a backend message to the frontend Message shape.
 *  @param viewerRole - 'gp' shows currentUser for GP messages, 'specialist' shows currentUser for specialist messages. */
export function toFrontendMessage(msg: BackendMessage, currentUser: string, viewerRole: 'gp' | 'specialist' = 'gp'): Message {
  const isAI = msg.sender === 'ai';
  const isSpecialist = msg.sender === 'specialist';

  let senderName: string;
  if (isAI) {
    senderName = 'NHS AI Assistant';
  } else if (viewerRole === 'specialist') {
    // Specialist viewer: own specialist messages show their name, GP messages show 'GP User'
    senderName = isSpecialist ? currentUser : 'GP User';
  } else {
    // GP viewer: own GP messages show their name, specialist messages show 'Specialist'
    senderName = isSpecialist ? 'Specialist' : currentUser;
  }

  return {
    id: String(msg.id),
    senderId: isAI ? 'ai' : isSpecialist ? 'specialist' : 'user',
    senderName,
    senderType: isAI ? 'ai' : isSpecialist ? 'specialist' : 'gp',
    content: msg.content,
    timestamp: new Date(msg.created_at),
    citations: mapCitations(
      (msg.citations_used as unknown[] | null) ?? msg.citations_used,
      (msg.citations as unknown[] | null) ?? (msg.citations_retrieved as unknown[] | null),
    ),
    isGenerating: msg.is_generating ?? false,
    reviewStatus: msg.review_status ?? null,
    reviewFeedback: msg.review_feedback ?? null,
    reviewedAt: msg.reviewed_at ?? null,
  };
}
