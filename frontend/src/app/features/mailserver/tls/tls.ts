import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';

import { MailserverService } from '../../../core/mailserver.service';
import { TlsCertificate } from '../../../core/mailserver.models';
import { mailserverErrorMessage } from '../mailserver.utils';

/** The TLS certificate Postfix serves, read from the path it actually uses. */
@Component({
  selector: 'app-mailserver-tls',
  templateUrl: './tls.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Tls {
  private readonly mailserver = inject(MailserverService);

  protected readonly certificate = signal<TlsCertificate | null>(null);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);

  /** Bootstrap contextual class reflecting how close the certificate is to expiry. */
  protected readonly expiryClass = computed(() => {
    const days = this.certificate()?.days_remaining;
    if (days === null || days === undefined) {
      return 'text-bg-secondary';
    }
    if (days < 0) {
      return 'text-bg-danger';
    }
    return days < 15 ? 'text-bg-warning' : 'text-bg-success';
  });

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      this.certificate.set(await this.mailserver.getTlsCertificate());
    } catch (err) {
      this.error.set(mailserverErrorMessage(err));
    } finally {
      this.loading.set(false);
    }
  }

  protected refresh(): void {
    void this.load();
  }
}
