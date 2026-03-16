import type { BackendMessage } from '../types/api';
import type { Message, Citation } from '../types';

type RawCitation = Record<string, unknown> & {
  metadata?: Record<string, unknown>;
};

/** Safely map raw citation objects coming from the backend to the frontend Citation shape. */
export function mapCitations(raw?: unknown[] | null, fallback?: unknown[] | null): Citation[] {
  const list = Array.isArray(raw)
    ? raw
    : Array.isArray(fallback)
      ? fallback
      : [];

  return list
    .map((entry) => {
      if (!entry || typeof entry !== 'object') return null;
      const citation = entry as RawCitation;
      const meta = citation.metadata || {};
      const docId = citation.doc_id ?? meta.doc_id;
      const sectionPath = citation.section_path ?? meta.section_path;
      const pageStart = citation.page_start ?? meta.page_start;
      const pageEnd = citation.page_end ?? meta.page_end;
      const creationDate = citation.creation_date ?? meta.creation_date;
      const publishDate = citation.publish_date ?? meta.publish_date;
      const lastUpdatedDate = citation.last_updated_date ?? meta.last_updated_date;

      return {
        doc_id: typeof docId === 'string' ? docId : undefined,
        title:
          readString(citation.title)
          || readString(meta.title)
          || readString(meta.filename)
          || readString(citation.source)
          || 'Source',
        source_name:
          readString(citation.source_name)
          || readString(meta.source_name)
          || readString(citation.source)
          || 'Source',
        specialty: readString(citation.specialty) || readString(meta.specialty),
        section_path: sectionPath,
        page_start: typeof pageStart === 'number' ? pageStart : undefined,
        page_end: typeof pageEnd === 'number' ? pageEnd : undefined,
        source_url: readString(citation.source_url) || readString(meta.source_url),
        creation_date: typeof creationDate === 'string' ? creationDate : undefined,
        publish_date: typeof publishDate === 'string' ? publishDate : undefined,
        last_updated_date: typeof lastUpdatedDate === 'string' ? lastUpdatedDate : undefined,
      } satisfies Citation;
    })
    .filter(Boolean) as Citation[];
}

function readString(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
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
      (msg as BackendMessage & { citations_used?: unknown[] | null }).citations_used,
      msg.citations,
    ),
    isGenerating: msg.is_generating ?? false,
    reviewStatus: msg.review_status ?? null,
    reviewFeedback: msg.review_feedback ?? null,
    reviewedAt: msg.reviewed_at ?? null,
  };
}
