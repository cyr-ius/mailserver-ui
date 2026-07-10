import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { form, FormField, required, submit } from '@angular/forms/signals';

import { MailserverService } from '../../../core/mailserver.service';
import { DovecotMaster } from '../../../core/mailserver.models';
import { mailserverErrorMessage } from '../mailserver.utils';

/** Dovecot master accounts and the raw dovecot.cf override. */
@Component({
  selector: 'app-mailserver-dovecot',
  imports: [FormField],
  templateUrl: './dovecot.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Dovecot {
  private readonly mailserver = inject(MailserverService);

  protected readonly masters = signal<DovecotMaster[]>([]);
  protected readonly config = signal('');
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly success = signal<string | null>(null);
  protected readonly creatingMaster = signal(false);
  protected readonly deletingMaster = signal<string | null>(null);
  protected readonly savingConfig = signal(false);

  protected readonly masterModel = signal({ name: '', password: '' });
  protected readonly masterForm = form(this.masterModel, (path) => {
    required(path.name, { message: 'A name is required' });
    required(path.password, { message: 'A password is required' });
  });

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const [masters, config] = await Promise.all([
        this.mailserver.listDovecotMasters(),
        this.mailserver.getDovecotConfig(),
      ]);
      this.masters.set(masters);
      this.config.set(config.content);
    } catch {
      this.error.set('Unable to load the Dovecot configuration.');
    } finally {
      this.loading.set(false);
    }
  }

  protected onCreateMaster(): void {
    this.error.set(null);
    this.success.set(null);
    submit(this.masterForm, async () => {
      const value = this.masterModel();
      const name = value.name.trim().toLowerCase();
      if (name.includes('@')) {
        this.error.set("A master name must not contain '@'.");
        return;
      }
      this.creatingMaster.set(true);
      try {
        await this.mailserver.createDovecotMaster({ name, password: value.password });
        this.success.set(`Master account ${name} created.`);
        this.masterModel.set({ name: '', password: '' });
        await this.load();
      } catch (err) {
        this.error.set(mailserverErrorMessage(err));
      } finally {
        this.creatingMaster.set(false);
      }
    });
  }

  protected async onDeleteMaster(master: DovecotMaster): Promise<void> {
    if (!confirm(`Delete the Dovecot master account ${master.name}?`)) {
      return;
    }
    this.error.set(null);
    this.success.set(null);
    this.deletingMaster.set(master.name);
    try {
      await this.mailserver.deleteDovecotMaster(master.name);
      this.success.set(`Master account ${master.name} deleted.`);
      await this.load();
    } catch (err) {
      this.error.set(mailserverErrorMessage(err));
    } finally {
      this.deletingMaster.set(null);
    }
  }

  protected onConfig(event: Event): void {
    this.config.set((event.target as HTMLTextAreaElement).value);
  }

  protected async onSaveConfig(): Promise<void> {
    this.error.set(null);
    this.success.set(null);
    this.savingConfig.set(true);
    try {
      const config = await this.mailserver.setDovecotConfig(this.config());
      this.config.set(config.content);
      this.success.set('Dovecot configuration saved. Restart the mailserver to apply it.');
    } catch (err) {
      this.error.set(mailserverErrorMessage(err));
    } finally {
      this.savingConfig.set(false);
    }
  }
}
