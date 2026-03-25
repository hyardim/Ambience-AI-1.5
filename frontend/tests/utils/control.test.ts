import { describe, expect, it, vi } from 'vitest';
import { filesFromInput, runUnlessSilent } from '@/utils/control';

describe('control utils', () => {
  it('runs callbacks only when not silent', () => {
    const callback = vi.fn();

    runUnlessSilent(false, callback);
    runUnlessSilent(undefined, callback);
    runUnlessSilent(true, callback);

    expect(callback).toHaveBeenCalledTimes(2);
  });

  it('converts file inputs to arrays', () => {
    const file = new File(['hello'], 'hello.txt', { type: 'text/plain' });
    const files = {
      0: file,
      length: 1,
      item: (index: number) => (index === 0 ? file : null),
    } as unknown as FileList;

    expect(filesFromInput(files)).toEqual([file]);
    expect(filesFromInput(null)).toEqual([]);
  });
});
