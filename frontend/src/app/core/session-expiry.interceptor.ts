import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';

import { SessionExpiryService } from './session-expiry.service';

/**
 * Endpoints whose 401 is a normal outcome rather than an expired session:
 * wrong credentials on sign-in, and the session probe run by the guards.
 */
const IGNORED_PATHS = ['/api/auth/login', '/api/auth/me', '/api/auth/config', '/api/auth/logout'];

function isIgnored(url: string): boolean {
  return IGNORED_PATHS.some((path) => url.startsWith(path));
}

/**
 * Turn a 401 raised on an established session into a global expiry signal, so
 * the shell can prompt for a new sign-in instead of leaving the page silently
 * stale. The error still propagates to the caller.
 */
export const sessionExpiryInterceptor: HttpInterceptorFn = (req, next) => {
  const sessionExpiry = inject(SessionExpiryService);

  return next(req).pipe(
    catchError((error: unknown) => {
      if (error instanceof HttpErrorResponse && error.status === 401 && !isIgnored(req.url)) {
        sessionExpiry.notifyExpired();
      }
      return throwError(() => error);
    }),
  );
};
