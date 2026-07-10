import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { form, FormField, required, submit } from '@angular/forms/signals';

import { MailserverService } from '../../../core/mailserver.service';
import { RelayExclusion, RelayHost } from '../../../core/mailserver.models';
import { mailserverErrorMessage } from '../mailserver.utils';

/** Outgoing mail routed through an external smarthost, per sender domain. */
@Component({
  selector: 'app-mailserver-relay',
  imports: [FormField],
  templateUrl: './relay.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Relay {
  private readonly mailserver = inject(MailserverService);

  protected readonly relays = signal<RelayHost[]>([]);
  protected readonly exclusions = signal<RelayExclusion[]>([]);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly success = signal<string | null>(null);

  protected readonly creatingRelay = signal(false);
  protected readonly createRelayError = signal<string | null>(null);
  protected readonly deletingSender = signal<string | null>(null);
  protected readonly relayModel = signal({
    sender: '',
    host: '',
    port: 587,
    username: '',
    password: '',
  });
  protected readonly relayForm = form(this.relayModel, (path) => {
    required(path.sender, { message: 'A sender domain is required' });
    required(path.host, { message: 'A relay host is required' });
  });

  protected readonly addingExclusion = signal(false);
  protected readonly deletingExclusion = signal<string | null>(null);
  protected readonly exclusionModel = signal({ sender: '' });
  protected readonly exclusionForm = form(this.exclusionModel, (path) => {
    required(path.sender, { message: 'A sender domain is required' });
  });

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const [relays, exclusions] = await Promise.all([
        this.mailserver.listRelays(),
        this.mailserver.listRelayExclusions(),
      ]);
      this.relays.set(relays);
      this.exclusions.set(exclusions);
    } catch {
      this.error.set('Unable to load the SMTP relays.');
    } finally {
      this.loading.set(false);
    }
  }

  protected onCreateRelay(): void {
    this.createRelayError.set(null);
    this.success.set(null);
    submit(this.relayForm, async () => {
      const value = this.relayModel();
      const sender = value.sender.trim().toLowerCase();
      if (!sender.includes('@')) {
        this.createRelayError.set('The sender must be a domain (e.g. @example.com).');
        return;
      }
      const port = Number(value.port);
      if (!Number.isInteger(port) || port < 1 || port > 65535) {
        this.createRelayError.set('The port must be between 1 and 65535.');
        return;
      }
      this.creatingRelay.set(true);
      try {
        await this.mailserver.createRelay({
          sender,
          host: value.host.trim(),
          port,
          username: value.username.trim() || null,
          password: value.password || null,
        });
        this.success.set(`Relay for ${sender} saved.`);
        this.relayModel.set({ sender: '', host: '', port: 587, username: '', password: '' });
        await this.load();
      } catch (err) {
        this.createRelayError.set(mailserverErrorMessage(err));
      } finally {
        this.creatingRelay.set(false);
      }
    });
  }

  protected async onDeleteRelay(relay: RelayHost): Promise<void> {
    if (!confirm(`Delete the SMTP relay for ${relay.sender}?`)) {
      return;
    }
    this.error.set(null);
    this.success.set(null);
    this.deletingSender.set(relay.sender);
    try {
      await this.mailserver.deleteRelay(relay.sender);
      this.success.set(`Relay for ${relay.sender} deleted.`);
      await this.load();
    } catch (err) {
      this.error.set(mailserverErrorMessage(err));
    } finally {
      this.deletingSender.set(null);
    }
  }

  protected onAddExclusion(): void {
    this.error.set(null);
    this.success.set(null);
    submit(this.exclusionForm, async () => {
      const sender = this.exclusionModel().sender.trim().toLowerCase();
      if (!sender.includes('@')) {
        this.error.set('The sender must be a domain (e.g. @example.com).');
        return;
      }
      this.addingExclusion.set(true);
      try {
        await this.mailserver.createRelayExclusion(sender);
        this.success.set(`${sender} will no longer use the global relay.`);
        this.exclusionModel.set({ sender: '' });
        await this.load();
      } catch (err) {
        this.error.set(mailserverErrorMessage(err));
      } finally {
        this.addingExclusion.set(false);
      }
    });
  }

  protected async onDeleteExclusion(exclusion: RelayExclusion): Promise<void> {
    if (!confirm(`Send mail from ${exclusion.sender} through the global relay again?`)) {
      return;
    }
    this.error.set(null);
    this.success.set(null);
    this.deletingExclusion.set(exclusion.sender);
    try {
      await this.mailserver.deleteRelayExclusion(exclusion.sender);
      this.success.set(`Exclusion for ${exclusion.sender} removed.`);
      await this.load();
    } catch (err) {
      this.error.set(mailserverErrorMessage(err));
    } finally {
      this.deletingExclusion.set(null);
    }
  }
}
