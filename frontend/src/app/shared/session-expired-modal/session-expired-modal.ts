import {
  ChangeDetectionStrategy,
  Component,
  DOCUMENT,
  ElementRef,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { Router } from '@angular/router';

import { AuthService } from '../../core/auth.service';
import { SessionExpiryService } from '../../core/session-expiry.service';

/** Bootstrap keeps the page from scrolling behind an open modal with this class. */
const BODY_MODAL_CLASS = 'modal-open';

/**
 * Blocking dialog shown when the backend rejects the session. It offers no way
 * out other than signing in again: every API call would fail anyway.
 */
@Component({
  selector: 'app-session-expired-modal',
  templateUrl: './session-expired-modal.html',
  styleUrl: './session-expired-modal.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SessionExpiredModal {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly sessionExpiry = inject(SessionExpiryService);
  private readonly body = inject(DOCUMENT).body;

  private readonly signInButton = viewChild<ElementRef<HTMLButtonElement>>('signIn');

  protected readonly expired = this.sessionExpiry.expired;
  protected readonly signingIn = signal(false);

  constructor() {
    effect(() => {
      this.body.classList.toggle(BODY_MODAL_CLASS, this.expired());
    });

    // The dialog appears on any screen: move focus onto its only action so the
    // keyboard never stays behind the backdrop.
    effect(() => {
      this.signInButton()?.nativeElement.focus();
    });
  }

  protected async onSignIn(): Promise<void> {
    this.signingIn.set(true);
    try {
      // Drops the stale cookie server-side; local state is cleared either way.
      await this.auth.logout();
      await this.router.navigate(['/login']);
    } finally {
      this.sessionExpiry.clear();
      this.signingIn.set(false);
    }
  }
}
