import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';

import { MailserverService } from '../../../core/mailserver.service';
import { DomainDnsRecords } from '../../../core/mailserver.models';
import { copyText } from '../mailserver.utils';

/** The MX, SPF, DMARC and DKIM records to publish for each hosted domain. */
@Component({
  selector: 'app-mailserver-dns',
  templateUrl: './dns.html',
  styleUrl: './dns.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Dns {
  private readonly mailserver = inject(MailserverService);

  protected readonly records = signal<DomainDnsRecords[]>([]);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      this.records.set(await this.mailserver.listDnsRecords());
    } catch {
      this.error.set('Unable to load the DNS records.');
    } finally {
      this.loading.set(false);
    }
  }

  protected copy(text: string): void {
    void copyText(text);
  }
}
