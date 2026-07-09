import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { Role, roleGrants } from './auth.models';
import { AuthService } from './auth.service';

/** Ensure the session has been probed at least once before deciding. */
async function ensureLoaded(auth: AuthService): Promise<void> {
  if (!auth.loaded()) {
    await auth.refreshSession();
  }
}

/**
 * Build a guard requiring at least `required`. Anonymous visitors go to /login;
 * authenticated users lacking the role fall back to the dashboard, which every
 * role can reach.
 */
function requireRole(required: Role): CanActivateFn {
  return async () => {
    const auth = inject(AuthService);
    const router = inject(Router);

    await ensureLoaded(auth);
    if (!auth.isAuthenticated()) {
      return router.createUrlTree(['/login']);
    }
    if (roleGrants(auth.user()?.role, required)) {
      return true;
    }
    return router.createUrlTree(['/dashboard']);
  };
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

/** Guard protecting admin-only routes; redirects everyone else to /dashboard. */
export const adminGuard: CanActivateFn = requireRole('admin');

/** Guard protecting the Mailbox section; open to managers and administrators. */
export const mailboxManagerGuard: CanActivateFn = requireRole('mailbox_manager');

/** Guard for the login page; sends already-authenticated users to /dashboard. */
export const guestGuard: CanActivateFn = async () => {
  const auth = inject(AuthService);
  const router = inject(Router);

  await ensureLoaded(auth);
  if (auth.isAuthenticated()) {
    return router.createUrlTree(['/dashboard']);
  }
  return true;
};
