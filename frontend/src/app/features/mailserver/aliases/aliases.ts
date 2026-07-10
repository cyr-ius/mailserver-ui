import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { form, FormField, required, submit } from '@angular/forms/signals';

import { MailserverService } from '../../../core/mailserver.service';
import { RegexAlias, SystemAlias } from '../../../core/mailserver.models';
import { mailserverErrorMessage, parseTargets } from '../mailserver.utils';

/** Local system aliases and PCRE aliases, which mailbox forwarding cannot express. */
@Component({
  selector: 'app-mailserver-aliases',
  imports: [FormField],
  templateUrl: './aliases.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Aliases {
  private readonly mailserver = inject(MailserverService);

  protected readonly systemAliases = signal<SystemAlias[]>([]);
  protected readonly regexAliases = signal<RegexAlias[]>([]);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly success = signal<string | null>(null);
  protected readonly addingSystemAlias = signal(false);
  protected readonly addingRegexAlias = signal(false);
  protected readonly deletingAlias = signal<string | null>(null);

  protected readonly systemAliasModel = signal({ name: '', targets: '' });
  protected readonly systemAliasForm = form(this.systemAliasModel, (path) => {
    required(path.name, { message: 'An alias name is required' });
    required(path.targets, { message: 'At least one destination is required' });
  });
  protected readonly regexAliasModel = signal({ pattern: '', targets: '' });
  protected readonly regexAliasForm = form(this.regexAliasModel, (path) => {
    required(path.pattern, { message: 'A pattern is required' });
    required(path.targets, { message: 'At least one destination is required' });
  });

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const [system, regex] = await Promise.all([
        this.mailserver.listSystemAliases(),
        this.mailserver.listRegexAliases(),
      ]);
      this.systemAliases.set(system);
      this.regexAliases.set(regex);
    } catch {
      this.error.set('Unable to load the aliases.');
    } finally {
      this.loading.set(false);
    }
  }

  protected onAddSystemAlias(): void {
    this.error.set(null);
    this.success.set(null);
    submit(this.systemAliasForm, async () => {
      const value = this.systemAliasModel();
      const name = value.name.trim().toLowerCase();
      if (name.includes('@')) {
        this.error.set('A system alias is a local name, without a domain.');
        return;
      }
      const targets = parseTargets(value.targets);
      if (targets.length === 0) {
        this.error.set('At least one destination is required.');
        return;
      }
      this.addingSystemAlias.set(true);
      try {
        await this.mailserver.createSystemAlias(name, targets);
        this.success.set(`System alias ${name} created.`);
        this.systemAliasModel.set({ name: '', targets: '' });
        await this.load();
      } catch (err) {
        this.error.set(mailserverErrorMessage(err));
      } finally {
        this.addingSystemAlias.set(false);
      }
    });
  }

  protected async onDeleteSystemAlias(alias: SystemAlias): Promise<void> {
    if (!confirm(`Delete the system alias ${alias.name}?`)) {
      return;
    }
    this.error.set(null);
    this.success.set(null);
    this.deletingAlias.set(alias.name);
    try {
      await this.mailserver.deleteSystemAlias(alias.name);
      this.success.set(`System alias ${alias.name} deleted.`);
      await this.load();
    } catch (err) {
      this.error.set(mailserverErrorMessage(err));
    } finally {
      this.deletingAlias.set(null);
    }
  }

  protected onAddRegexAlias(): void {
    this.error.set(null);
    this.success.set(null);
    submit(this.regexAliasForm, async () => {
      const value = this.regexAliasModel();
      const pattern = value.pattern.trim();
      if (!/^\/.+\/[imxs]*$/.test(pattern)) {
        this.error.set('A regex alias must be delimited by slashes, e.g. /^info@.+$/.');
        return;
      }
      const targets = parseTargets(value.targets);
      if (targets.length === 0) {
        this.error.set('At least one destination is required.');
        return;
      }
      this.addingRegexAlias.set(true);
      try {
        await this.mailserver.createRegexAlias(pattern, targets);
        this.success.set('Regex alias created.');
        this.regexAliasModel.set({ pattern: '', targets: '' });
        await this.load();
      } catch (err) {
        this.error.set(mailserverErrorMessage(err));
      } finally {
        this.addingRegexAlias.set(false);
      }
    });
  }

  protected async onDeleteRegexAlias(alias: RegexAlias): Promise<void> {
    if (!confirm(`Delete the regex alias ${alias.pattern}?`)) {
      return;
    }
    this.error.set(null);
    this.success.set(null);
    this.deletingAlias.set(alias.pattern);
    try {
      await this.mailserver.deleteRegexAlias(alias.pattern);
      this.success.set('Regex alias deleted.');
      await this.load();
    } catch (err) {
      this.error.set(mailserverErrorMessage(err));
    } finally {
      this.deletingAlias.set(null);
    }
  }
}
