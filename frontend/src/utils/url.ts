export function setOptionalSearchParam(
  params: URLSearchParams,
  key: string,
  value: string | number | undefined,
): void {
  if (value) {
    params.set(key, String(value));
  }
}
