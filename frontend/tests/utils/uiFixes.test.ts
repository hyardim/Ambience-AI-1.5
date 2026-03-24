/**
 * Tests for UI fix logic introduced in feature/rag-updates:
 *
 * 1. Citation URL page anchor (#page=N)
 * 2. New consultation form validation (title, message, age)
 * 3. Manual response file size validation (10 MB limit)
 * 4. Profile password strength enforcement
 * 5. Login 401 error message
 */

import { describe, expect, it } from 'vitest';

// ---------------------------------------------------------------------------
// 1. Citation page anchor
// ---------------------------------------------------------------------------

/**
 * Mirrors the href-building logic in ChatMessage.tsx:
 *   c.source_url && c.page_start → `${source_url}#page=${page_start}`
 */
function buildCitationHref(sourceUrl: string | undefined, pageStart: number | undefined): string | undefined {
  return sourceUrl
    ? pageStart
      ? `${sourceUrl}#page=${pageStart}`
      : sourceUrl
    : undefined;
}

describe('buildCitationHref', () => {
  it('appends #page=N when source_url and page_start are present', () => {
    expect(buildCitationHref(
      'https://www.nice.org.uk/guidance/ng226/resources/osteoarthritis-pdf-123',
      16,
    )).toBe('https://www.nice.org.uk/guidance/ng226/resources/osteoarthritis-pdf-123#page=16');
  });

  it('returns source_url unchanged when no page_start', () => {
    expect(buildCitationHref(
      'https://www.nice.org.uk/guidance/ng226/resources/osteoarthritis-pdf-123',
      undefined,
    )).toBe('https://www.nice.org.uk/guidance/ng226/resources/osteoarthritis-pdf-123');
  });

  it('returns undefined when source_url is absent', () => {
    expect(buildCitationHref(undefined, 5)).toBeUndefined();
    expect(buildCitationHref(undefined, undefined)).toBeUndefined();
  });

  it('works with page 1', () => {
    expect(buildCitationHref('https://example.com/doc.pdf', 1))
      .toBe('https://example.com/doc.pdf#page=1');
  });
});

// ---------------------------------------------------------------------------
// 2. New consultation form validation
// ---------------------------------------------------------------------------

interface ConsultationFormData {
  title: string;
  message: string;
  specialty: string;
  patientAge: string;
  sex: string;
  severity: string;
}

function validateConsultationForm(data: ConsultationFormData): string | null {
  if (!data.title.trim()) return 'Please enter a consultation title.';
  if (!data.message.trim()) return 'Please enter a clinical question before submitting.';
  if (!data.specialty) return 'Please select a specialty before submitting. Without it, the consultation cannot be routed to a specialist.';
  if (!data.patientAge) return "Please enter the patient's age.";
  const age = parseInt(data.patientAge, 10);
  if (isNaN(age) || age < 0 || age > 150) return 'Please enter a valid patient age between 0 and 150.';
  if (!data.sex) return "Please select the patient's sex.";
  if (!data.severity) return 'Please select urgency.';
  return null;
}

const validForm: ConsultationFormData = {
  title: 'Test Consultation',
  message: 'What is the treatment for RA?',
  specialty: 'rheumatology',
  patientAge: '45',
  sex: 'female',
  severity: 'medium',
};

describe('validateConsultationForm', () => {
  it('passes with all valid fields', () => {
    expect(validateConsultationForm(validForm)).toBeNull();
  });

  it('requires a non-empty title', () => {
    expect(validateConsultationForm({ ...validForm, title: '' }))
      .toBe('Please enter a consultation title.');
    expect(validateConsultationForm({ ...validForm, title: '   ' }))
      .toBe('Please enter a consultation title.');
  });

  it('requires a non-empty clinical question', () => {
    expect(validateConsultationForm({ ...validForm, message: '' }))
      .toBe('Please enter a clinical question before submitting.');
    expect(validateConsultationForm({ ...validForm, message: '  ' }))
      .toBe('Please enter a clinical question before submitting.');
  });

  it('requires a specialty', () => {
    expect(validateConsultationForm({ ...validForm, specialty: '' }))
      .toContain('Please select a specialty');
  });

  it('requires a patient age', () => {
    expect(validateConsultationForm({ ...validForm, patientAge: '' }))
      .toContain("Please enter the patient's age");
  });

  it('rejects age out of range', () => {
    expect(validateConsultationForm({ ...validForm, patientAge: '-1' }))
      .toBe('Please enter a valid patient age between 0 and 150.');
    expect(validateConsultationForm({ ...validForm, patientAge: '151' }))
      .toBe('Please enter a valid patient age between 0 and 150.');
    expect(validateConsultationForm({ ...validForm, patientAge: 'abc' }))
      .toBe('Please enter a valid patient age between 0 and 150.');
  });

  it('accepts edge-case ages 0 and 150', () => {
    expect(validateConsultationForm({ ...validForm, patientAge: '0' })).toBeNull();
    expect(validateConsultationForm({ ...validForm, patientAge: '150' })).toBeNull();
  });

  it('requires sex', () => {
    expect(validateConsultationForm({ ...validForm, sex: '' }))
      .toContain("Please select the patient's sex");
  });
});

// ---------------------------------------------------------------------------
// 3. Manual response file size validation
// ---------------------------------------------------------------------------

const MAX_FILE_SIZE_MB = 10;
const MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024;

function validateManualResponseFiles(files: { name: string; size: number }[]): string | null {
  const oversized = files.filter(f => f.size > MAX_FILE_SIZE);
  if (oversized.length > 0) {
    return `File(s) exceed the ${MAX_FILE_SIZE_MB} MB limit: ${oversized.map(f => f.name).join(', ')}`;
  }
  return null;
}

describe('validateManualResponseFiles', () => {
  it('passes with no files', () => {
    expect(validateManualResponseFiles([])).toBeNull();
  });

  it('passes when all files are within the limit', () => {
    expect(validateManualResponseFiles([
      { name: 'guideline.pdf', size: 5 * 1024 * 1024 },
      { name: 'notes.txt', size: 1024 },
    ])).toBeNull();
  });

  it('fails when a file exceeds 10 MB', () => {
    const result = validateManualResponseFiles([
      { name: 'large.pdf', size: 11 * 1024 * 1024 },
    ]);
    expect(result).toContain('large.pdf');
    expect(result).toContain('10 MB');
  });

  it('lists all oversized files in the error', () => {
    const result = validateManualResponseFiles([
      { name: 'a.pdf', size: 11 * 1024 * 1024 },
      { name: 'b.pdf', size: 12 * 1024 * 1024 },
      { name: 'ok.pdf', size: 1 * 1024 * 1024 },
    ]);
    expect(result).toContain('a.pdf');
    expect(result).toContain('b.pdf');
    expect(result).not.toContain('ok.pdf');
  });

  it('passes a file exactly at the 10 MB limit', () => {
    expect(validateManualResponseFiles([
      { name: 'exact.pdf', size: MAX_FILE_SIZE },
    ])).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// 4. Profile password strength enforcement
// ---------------------------------------------------------------------------

function validateNewPassword(password: string): string | null {
  const strongEnough =
    password.length >= 8 &&
    /[A-Z]/.test(password) &&
    /[a-z]/.test(password) &&
    /\d/.test(password) &&
    /[!@#$%^&*()_+\-=[\]{}|;:'",.<>?/`~\\]/.test(password);
  if (!strongEnough) {
    return 'Password must be at least 8 characters and include uppercase, lowercase, a number, and a special character.';
  }
  return null;
}

describe('validateNewPassword', () => {
  it('accepts a strong password', () => {
    expect(validateNewPassword('Password123!')).toBeNull();
    expect(validateNewPassword('SecureP@ss1')).toBeNull();
  });

  it('rejects passwords shorter than 8 characters', () => {
    expect(validateNewPassword('Ab1!')).not.toBeNull();
  });

  it('rejects passwords without uppercase', () => {
    expect(validateNewPassword('password123!')).not.toBeNull();
  });

  it('rejects passwords without lowercase', () => {
    expect(validateNewPassword('PASSWORD123!')).not.toBeNull();
  });

  it('rejects passwords without a digit', () => {
    expect(validateNewPassword('PasswordABC!')).not.toBeNull();
  });

  it('rejects passwords without a special character', () => {
    expect(validateNewPassword('Password123')).not.toBeNull();
  });

  it('rejects an empty password', () => {
    expect(validateNewPassword('')).not.toBeNull();
  });
});

// ---------------------------------------------------------------------------
// 5. Full name length validation
// ---------------------------------------------------------------------------

function validateFullName(name: string): string | null {
  if (name.trim().length > 100) {
    return 'Full name must be 100 characters or fewer.';
  }
  return null;
}

describe('validateFullName', () => {
  it('passes a normal name', () => {
    expect(validateFullName('Dr. Jane Smith')).toBeNull();
  });

  it('passes an empty name (optional field)', () => {
    expect(validateFullName('')).toBeNull();
  });

  it('passes a name exactly 100 characters long', () => {
    expect(validateFullName('A'.repeat(100))).toBeNull();
  });

  it('rejects a name over 100 characters', () => {
    expect(validateFullName('A'.repeat(101)))
      .toBe('Full name must be 100 characters or fewer.');
  });
});

// ---------------------------------------------------------------------------
// 6. Login 401 error message
// ---------------------------------------------------------------------------

function getLoginErrorMessage(status: number, url: string): string {
  if (status === 401) {
    if (url.includes('/auth/login')) return 'Incorrect email or password';
    return 'Session expired';
  }
  return `Request failed (${status})`;
}

describe('getLoginErrorMessage', () => {
  it('returns "Incorrect email or password" for 401 on login endpoint', () => {
    expect(getLoginErrorMessage(401, '/auth/login')).toBe('Incorrect email or password');
  });

  it('returns "Session expired" for 401 on other endpoints', () => {
    expect(getLoginErrorMessage(401, '/api/chats')).toBe('Session expired');
    expect(getLoginErrorMessage(401, '/auth/refresh')).toBe('Session expired');
  });

  it('returns generic message for other status codes', () => {
    expect(getLoginErrorMessage(500, '/auth/login')).toBe('Request failed (500)');
    expect(getLoginErrorMessage(403, '/api/chats')).toBe('Request failed (403)');
  });
});

// ---------------------------------------------------------------------------
// 7. Duplicate file detection (ChatInput)
// ---------------------------------------------------------------------------

/**
 * Mirrors the dedup logic in ChatInput.tsx handleFileChange:
 *   existing = set of filenames already in the chat (existingFileNames + pending)
 *   duplicates = selected files whose name is already in existing
 *   incoming  = selected files whose name is NOT in existing
 */
interface FileCandidate { name: string }

function filterIncomingFiles(
  selected: FileCandidate[],
  existingFileNames: string[],
  pendingFileNames: string[] = [],
): { incoming: FileCandidate[]; duplicates: FileCandidate[] } {
  const currentNames = new Set([...existingFileNames, ...pendingFileNames]);
  return {
    incoming: selected.filter(f => !currentNames.has(f.name)),
    duplicates: selected.filter(f => currentNames.has(f.name)),
  };
}

describe('filterIncomingFiles', () => {
  it('accepts all files when there are no existing files', () => {
    const { incoming, duplicates } = filterIncomingFiles(
      [{ name: 'report.pdf' }, { name: 'notes.txt' }],
      [],
    );
    expect(incoming).toHaveLength(2);
    expect(duplicates).toHaveLength(0);
  });

  it('rejects a file whose name matches an existing chat file', () => {
    const { incoming, duplicates } = filterIncomingFiles(
      [{ name: 'report.pdf' }],
      ['report.pdf'],
    );
    expect(incoming).toHaveLength(0);
    expect(duplicates).toHaveLength(1);
    expect(duplicates[0].name).toBe('report.pdf');
  });

  it('rejects a file whose name matches a pending (not yet sent) file', () => {
    const { incoming, duplicates } = filterIncomingFiles(
      [{ name: 'labs.pdf' }],
      [],
      ['labs.pdf'],
    );
    expect(incoming).toHaveLength(0);
    expect(duplicates[0].name).toBe('labs.pdf');
  });

  it('splits a mixed selection into incoming and duplicates correctly', () => {
    const { incoming, duplicates } = filterIncomingFiles(
      [{ name: 'new.pdf' }, { name: 'old.pdf' }, { name: 'also-new.txt' }],
      ['old.pdf'],
    );
    expect(incoming.map(f => f.name)).toEqual(['new.pdf', 'also-new.txt']);
    expect(duplicates.map(f => f.name)).toEqual(['old.pdf']);
  });

  it('rejects all files when every selected file is a duplicate', () => {
    const { incoming, duplicates } = filterIncomingFiles(
      [{ name: 'a.pdf' }, { name: 'b.pdf' }],
      ['a.pdf', 'b.pdf'],
    );
    expect(incoming).toHaveLength(0);
    expect(duplicates).toHaveLength(2);
  });

  it('is case-sensitive (Report.pdf ≠ report.pdf)', () => {
    const { incoming, duplicates } = filterIncomingFiles(
      [{ name: 'Report.pdf' }],
      ['report.pdf'],
    );
    expect(incoming).toHaveLength(1);
    expect(duplicates).toHaveLength(0);
  });

  it('handles an empty selection without error', () => {
    const { incoming, duplicates } = filterIncomingFiles([], ['existing.pdf']);
    expect(incoming).toHaveLength(0);
    expect(duplicates).toHaveLength(0);
  });

  it('deduplicates against both existing chat files and pending files simultaneously', () => {
    const { incoming, duplicates } = filterIncomingFiles(
      [{ name: 'chat-file.pdf' }, { name: 'pending-file.pdf' }, { name: 'fresh.pdf' }],
      ['chat-file.pdf'],
      ['pending-file.pdf'],
    );
    expect(incoming.map(f => f.name)).toEqual(['fresh.pdf']);
    expect(duplicates.map(f => f.name)).toEqual(['chat-file.pdf', 'pending-file.pdf']);
  });

  it('duplicate notice text contains the duplicate filename', () => {
    const { duplicates } = filterIncomingFiles(
      [{ name: 'guideline.pdf' }],
      ['guideline.pdf'],
    );
    const notice = duplicates.length > 0
      ? `Already in this chat: ${duplicates.map(f => f.name).join(', ')}`
      : null;
    expect(notice).toBe('Already in this chat: guideline.pdf');
  });

  it('duplicate notice lists multiple filenames separated by commas', () => {
    const { duplicates } = filterIncomingFiles(
      [{ name: 'a.pdf' }, { name: 'b.pdf' }],
      ['a.pdf', 'b.pdf'],
    );
    const notice = `Already in this chat: ${duplicates.map(f => f.name).join(', ')}`;
    expect(notice).toBe('Already in this chat: a.pdf, b.pdf');
  });
});

// ---------------------------------------------------------------------------
// 8. Per-chat file count limit (mirrors backend chat_uploads.py)
// ---------------------------------------------------------------------------

const MAX_FILES_PER_CHAT = 5;

function checkFileCountLimit(existingCount: number): string | null {
  if (existingCount >= MAX_FILES_PER_CHAT) {
    return `Chat already has ${existingCount} files. Maximum is ${MAX_FILES_PER_CHAT}.`;
  }
  return null;
}

describe('checkFileCountLimit', () => {
  it('allows upload when chat has no files', () => {
    expect(checkFileCountLimit(0)).toBeNull();
  });

  it('allows upload when chat has fewer than the maximum', () => {
    expect(checkFileCountLimit(1)).toBeNull();
    expect(checkFileCountLimit(4)).toBeNull();
  });

  it('blocks upload when chat is exactly at the limit', () => {
    expect(checkFileCountLimit(5)).not.toBeNull();
  });

  it('blocks upload when chat exceeds the limit', () => {
    expect(checkFileCountLimit(6)).not.toBeNull();
  });

  it('error message includes the current count and the maximum', () => {
    expect(checkFileCountLimit(5)).toBe('Chat already has 5 files. Maximum is 5.');
  });

  it('error message reflects the actual existing count when over limit', () => {
    expect(checkFileCountLimit(6)).toBe('Chat already has 6 files. Maximum is 5.');
  });

  it('allows upload at one below the limit (boundary)', () => {
    expect(checkFileCountLimit(MAX_FILES_PER_CHAT - 1)).toBeNull();
  });

  it('blocks upload at exactly the limit (boundary)', () => {
    expect(checkFileCountLimit(MAX_FILES_PER_CHAT)).not.toBeNull();
  });
});
