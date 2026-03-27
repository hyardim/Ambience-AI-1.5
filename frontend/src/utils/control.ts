export function runUnlessSilent(silent: boolean | undefined, callback: () => void): void {
  if (!silent) {
    callback();
  }
}

export function filesFromInput(files: FileList | null): File[] {
  return Array.from(files ?? []);
}
