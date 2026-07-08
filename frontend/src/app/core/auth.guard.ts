import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { AuthService } from './auth.service';

/** Ensure the session has been probed at least once before deciding. */
async function ensureLoaded(auth: AuthService): Promise<void> {
  if (!auth.loaded()) {
    await auth.refreshSession();
  }
}

/** Guard protecting authenticated routes; redirects to /login otherwise. */
export const authGuard: CanActivateFn = async () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  await ensureLoaded(auth);
  if (auth.isAuthenticated()) {
    return true;
  }
  return router.createUrlTree(['/login']);
};

/** Guard protecting admin-only routes; redirects non-admins to /welcome. */
export const adminGuard: CanActivateFn = async () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  await ensureLoaded(auth);
  if (!auth.isAuthenticated()) {
    return router.createUrlTree(['/login']);
  }
  if (auth.user()?.role === 'admin') {
    return true;
  }
  return router.createUrlTree(['/welcome']);
};

/** Guard for the login page; sends already-authenticated users to /welcome. */
export const guestGuard: CanActivateFn = async () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  await ensureLoaded(auth);
  if (auth.isAuthenticated()) {
    return router.createUrlTree(['/welcome']);
  }
  return true;
};
