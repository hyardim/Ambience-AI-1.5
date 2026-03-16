import { describe, expect, it } from 'vitest';
import { formatAuditUserIdentifier } from '@/utils/audit';

describe('audit utils', () => {
  it('formats audit user identifiers consistently', () => {
    expect(formatAuditUserIdentifier('gp_1', 1)).toBe('gp_1');
    expect(formatAuditUserIdentifier('', 42)).toBe('#42');
    expect(formatAuditUserIdentifier(null, 0)).toBe('—');
  });
});
