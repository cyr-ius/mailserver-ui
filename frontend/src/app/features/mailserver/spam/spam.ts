import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';

import { MailserverService } from '../../../core/mailserver.service';
import { SpamConfigScope } from '../../../core/mailserver.models';
import { mailserverErrorMessage } from '../mailserver.utils';

/** What each editable spam-filtering file is, keyed by its scope. */
interface ScopeDescriptor {
  scope: SpamConfigScope;
  label: string;
  filename: string;
  /** The component reading the file, named as the warning names it. */
  feature: string;
  placeholder: string;
}

const SCOPES: readonly ScopeDescriptor[] = [
  {
    scope: 'rules',
    label: 'SpamAssassin rules',
    filename: 'spamassassin-rules.cf',
    feature: 'SpamAssassin',
    placeholder:
      'header LOCAL_DEMO_SUBJECT Subject =~ /\\bdemo\\b/i\nscore LOCAL_DEMO_SUBJECT 2.0\ndescribe LOCAL_DEMO_SUBJECT Subject mentions a demo',
  },
  {
    scope: 'whitelist-clients',
    label: 'Postgrey clients',
    filename: 'whitelist_clients.local',
    feature: 'Postgrey',
    placeholder: 'example.com\nmail.partner.example\n/^smtp[0-9]+\\.bulk\\.example$/',
  },
  {
    scope: 'whitelist-recipients',
    label: 'Postgrey recipients',
    filename: 'whitelist_recipients',
    feature: 'Postgrey',
    placeholder: 'postmaster@example.com\nsupport@example.com',
  },
  {
    scope: 'amavis',
    label: 'Amavis',
    filename: 'amavis.cf',
    feature: 'Amavis',
    placeholder:
      '$sa_tag_level_deflt = -999;\n$sa_tag2_level_deflt = 6.0;\n$sa_kill_level_deflt = 10.0;\n$final_spam_destiny = D_PASS;\n\n# Do not remove: Amavis requires the file to end with a true value.\n1;',
  },
];

/** The spam-filtering files docker-mailserver reads from the config volume. */
@Component({
  selector: 'app-mailserver-spam',
  templateUrl: './spam.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Spam {
  private readonly mailserver = inject(MailserverService);

  protected readonly scopes = SCOPES;
  protected readonly scope = signal<SpamConfigScope>('rules');
  protected readonly content = signal('');
  /** The ENABLE_* variable guarding the open file, and whether it is on. */
  protected readonly featureVariable = signal('');
  protected readonly featureEnabled = signal(true);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly success = signal<string | null>(null);
  protected readonly saving = signal(false);

  /** The descriptor of the file currently open; SCOPES always holds the scope. */
  protected readonly current = computed(
    () => SCOPES.find((entry) => entry.scope === this.scope()) ?? SCOPES[0],
  );

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const config = await this.mailserver.getSpamConfig(this.scope());
      this.content.set(config.content);
      this.featureVariable.set(config.feature);
      this.featureEnabled.set(config.feature_enabled);
    } catch (err) {
      this.error.set(mailserverErrorMessage(err));
    } finally {
      this.loading.set(false);
    }
  }

  protected setScope(scope: SpamConfigScope): void {
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
      const config = await this.mailserver.setSpamConfig(this.scope(), this.content());
      this.content.set(config.content);
      this.success.set(`${this.current().filename} was saved. Restart the mailserver to apply it.`);
    } catch (err) {
      this.error.set(mailserverErrorMessage(err));
    } finally {
      this.saving.set(false);
    }
  }
}
