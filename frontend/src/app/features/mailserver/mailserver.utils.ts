import { HttpErrorResponse } from '@angular/common/http';

/** Turn a failed mailserver API call into a message the tabs can display as-is. */
export function mailserverErrorMessage(err: unknown): string {
  if (err instanceof HttpErrorResponse) {
    if (err.status === 409) {
      return 'This entry already exists.';
    }
    if (err.status === 404) {
      return 'This entry no longer exists.';
    }
    if (err.status === 400) {
      return 'Invalid request. Check the values and the mailserver config volume.';
    }
    if (err.status === 422) {
      return 'Invalid input. Check the fields and try again.';
    }
    if (err.status === 502) {
      return 'The mailserver container could not be reached. Check the Docker socket mount.';
    }
  }
  return 'Something went wrong. Please try again.';
}

/** Copy a DNS or DKIM value to the clipboard. Access can be denied; ignore silently. */
export async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // Clipboard access can be denied; ignore silently.
  }
}

/** Split a comma-separated destination list into clean addresses. */
export function parseTargets(raw: string): string[] {
  return raw
    .split(',')
    .map((target) => target.trim())
    .filter(Boolean);
}
