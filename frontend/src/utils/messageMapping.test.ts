import { describe, it, expect } from 'vitest';
import { mapCitations, toFrontendMessage } from './messageMapping';
import type { BackendMessage } from '../types/api';

describe('mapCitations', () => {
  it('returns empty array for null/undefined input', () => {
    expect(mapCitations(null)).toEqual([]);
    expect(mapCitations(undefined)).toEqual([]);
    expect(mapCitations(null, null)).toEqual([]);
  });

  it('uses fallback when primary is empty', () => {
    const fallback = [{ metadata: { title: 'FallbackTitle' }, source: 'src' }];
    const result = mapCitations([], fallback);
    expect(result).toHaveLength(1);
    expect(result[0].title).toBe('FallbackTitle');
  });

  it('maps citation fields correctly', () => {
    const raw = [{
      doc_id: 'doc-1',
      metadata: {
        title: 'Test Doc',
        source_name: 'NICE',
        specialty: 'cardiology',
        source_url: 'https://example.com',
      },
      section_path: ['Section 1', 'Sub A'],
      page_start: 5,
      page_end: 10,
    }];

    const result = mapCitations(raw);
    expect(result).toHaveLength(1);
    expect(result[0]).toEqual({
      doc_id: 'doc-1',
      title: 'Test Doc',
      source_name: 'NICE',
      specialty: 'cardiology',
      section_path: ['Section 1', 'Sub A'],
      page_start: 5,
      page_end: 10,
      source_url: 'https://example.com',
    });
  });

  it('filters out non-object entries', () => {
    const raw = [null, undefined, 'string', { source: 'valid' }];
    const result = mapCitations(raw as unknown[]);
    expect(result).toHaveLength(1);
  });

  it('uses source as title fallback', () => {
    const raw = [{ source: 'MySource' }];
    const result = mapCitations(raw);
    expect(result[0].title).toBe('MySource');
    expect(result[0].source_name).toBe('MySource');
  });
});

describe('toFrontendMessage', () => {
  const baseMsg: BackendMessage = {
    id: 1,
    content: 'Hello',
    sender: 'user',
    created_at: '2025-01-01T10:00:00Z',
  };

  it('maps GP user message with gp viewerRole', () => {
    const result = toFrontendMessage(baseMsg, 'Dr Smith');
    expect(result.id).toBe('1');
    expect(result.senderId).toBe('user');
    expect(result.senderName).toBe('Dr Smith');
    expect(result.senderType).toBe('gp');
    expect(result.content).toBe('Hello');
  });

  it('maps AI message correctly', () => {
    const aiMsg = { ...baseMsg, sender: 'ai', is_generating: true };
    const result = toFrontendMessage(aiMsg, 'Dr Smith');
    expect(result.senderId).toBe('ai');
    expect(result.senderName).toBe('NHS AI Assistant');
    expect(result.senderType).toBe('ai');
    expect(result.isGenerating).toBe(true);
  });

  it('maps specialist message for GP viewer', () => {
    const specMsg = { ...baseMsg, sender: 'specialist' };
    const result = toFrontendMessage(specMsg, 'Dr Smith', 'gp');
    expect(result.senderName).toBe('Specialist');
    expect(result.senderType).toBe('specialist');
  });

  it('maps specialist message for specialist viewer', () => {
    const specMsg = { ...baseMsg, sender: 'specialist' };
    const result = toFrontendMessage(specMsg, 'Dr Jones', 'specialist');
    expect(result.senderName).toBe('Dr Jones');
    expect(result.senderType).toBe('specialist');
  });

  it('maps GP message for specialist viewer as GP User', () => {
    const result = toFrontendMessage(baseMsg, 'Dr Jones', 'specialist');
    expect(result.senderName).toBe('GP User');
  });

  it('maps review fields', () => {
    const reviewedMsg = {
      ...baseMsg,
      sender: 'ai',
      review_status: 'approved',
      review_feedback: 'Good',
      reviewed_at: '2025-01-01T12:00:00Z',
    };
    const result = toFrontendMessage(reviewedMsg, 'Dr Smith');
    expect(result.reviewStatus).toBe('approved');
    expect(result.reviewFeedback).toBe('Good');
    expect(result.reviewedAt).toBe('2025-01-01T12:00:00Z');
  });

  it('defaults isGenerating to false when not provided', () => {
    const result = toFrontendMessage(baseMsg, 'Dr Smith');
    expect(result.isGenerating).toBe(false);
  });
});
