import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { MailserverService } from '../../../core/mailserver.service';
import { MailserverEnvironment } from '../../../core/mailserver.models';
import { mailserverErrorMessage } from '../mailserver.utils';

/** The read-only environment the mailserver container started with. */
@Component({
  selector: 'app-mailserver-environment',
  templateUrl: './environment.html',
  imports: [RouterLink],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Environment {
  private readonly mailserver = inject(MailserverService);

  protected readonly environment = signal<MailserverEnvironment | null>(null);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);

  protected readonly entries = computed(() => Object.entries(this.environment()?.variables ?? {}));

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      this.environment.set(await this.mailserver.getEnvironment());
    } catch (err) {
      this.error.set(mailserverErrorMessage(err));
    } finally {
      this.loading.set(false);
    }
  }
}
