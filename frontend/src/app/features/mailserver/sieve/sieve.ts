import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';

import { MailserverService } from '../../../core/mailserver.service';
import { SieveScope } from '../../../core/mailserver.models';
import { mailserverErrorMessage } from '../mailserver.utils';

/** Global Sieve scripts compiled around the users' own filters. */
@Component({
  selector: 'app-mailserver-sieve',
  templateUrl: './sieve.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Sieve {
  private readonly mailserver = inject(MailserverService);

  protected readonly scope = signal<SieveScope>('before');
  protected readonly content = signal('');
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly success = signal<string | null>(null);
  protected readonly saving = signal(false);

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      this.content.set((await this.mailserver.getSieveScript(this.scope())).content);
    } catch {
      this.error.set('Unable to load the Sieve script.');
    } finally {
      this.loading.set(false);
    }
  }

  protected setScope(scope: SieveScope): void {
    if (this.scope() === scope) {
      return;
    }
    this.scope.set(scope);
    this.success.set(null);
    void this.load();
  }

  protected onContent(event: Event): void {
    this.content.set((event.target as HTMLTextAreaElement).value);
  }

  protected async onSave(): Promise<void> {
    this.error.set(null);
    this.success.set(null);
    this.saving.set(true);
    try {
      const script = await this.mailserver.setSieveScript(this.scope(), this.content());
      this.content.set(script.content);
      this.success.set(
        `The "${script.scope}" script was saved. Restart the mailserver to compile it.`,
      );
    } catch (err) {
      this.error.set(mailserverErrorMessage(err));
    } finally {
      this.saving.set(false);
    }
  }
}
