import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { form, FormField, required, submit } from '@angular/forms/signals';

import { MailserverService } from '../../../core/mailserver.service';
import { Restriction, RestrictionKind } from '../../../core/mailserver.models';
import { mailserverErrorMessage } from '../mailserver.utils';

/** Addresses and domains blocked from sending or receiving mail. */
@Component({
  selector: 'app-mailserver-restrictions',
  imports: [FormField],
  templateUrl: './restrictions.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Restrictions {
  private readonly mailserver = inject(MailserverService);

  protected readonly kind = signal<RestrictionKind>('send');
  protected readonly restrictions = signal<Restriction[]>([]);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly success = signal<string | null>(null);
  protected readonly adding = signal(false);
  protected readonly deleting = signal<string | null>(null);

  protected readonly restrictionModel = signal({ address: '' });
  protected readonly restrictionForm = form(this.restrictionModel, (path) => {
    required(path.address, { message: 'An address is required' });
  });

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      this.restrictions.set(await this.mailserver.listRestrictions(this.kind()));
    } catch {
      this.error.set('Unable to load the restrictions.');
    } finally {
      this.loading.set(false);
    }
  }

  protected setKind(kind: RestrictionKind): void {
    if (this.kind() === kind) {
      return;
    }
    this.kind.set(kind);
    this.success.set(null);
    void this.load();
  }

  protected onAdd(): void {
    this.error.set(null);
    this.success.set(null);
    submit(this.restrictionForm, async () => {
      const address = this.restrictionModel().address.trim().toLowerCase();
      if (!address.includes('@')) {
        this.error.set('The target must be an address or a domain (@example.com).');
        return;
      }
      this.adding.set(true);
      try {
        await this.mailserver.addRestriction(this.kind(), address);
        this.success.set(`${address} restricted.`);
        this.restrictionModel.set({ address: '' });
        await this.load();
      } catch (err) {
        this.error.set(mailserverErrorMessage(err));
      } finally {
        this.adding.set(false);
      }
    });
  }

  protected async onDelete(restriction: Restriction): Promise<void> {
    if (!confirm(`Remove the ${restriction.kind} restriction for ${restriction.address}?`)) {
      return;
    }
    this.error.set(null);
    this.success.set(null);
    this.deleting.set(restriction.address);
    try {
      await this.mailserver.deleteRestriction(restriction.kind, restriction.address);
      this.success.set(`${restriction.address} removed.`);
      await this.load();
    } catch (err) {
      this.error.set(mailserverErrorMessage(err));
    } finally {
      this.deleting.set(null);
    }
  }
}
