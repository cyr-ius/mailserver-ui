import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';

import { MailserverService } from '../../../core/mailserver.service';
import { PostfixMasterOverride, PostfixOverride } from '../../../core/mailserver.models';
import { mailserverErrorMessage } from '../mailserver.utils';

/** Extra parameters appended to Postfix main.cf and master.cf. */
@Component({
  selector: 'app-mailserver-postfix',
  templateUrl: './postfix.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Postfix {
  private readonly mailserver = inject(MailserverService);

  protected readonly overrides = signal<PostfixOverride[]>([]);
  protected readonly masterOverrides = signal<PostfixMasterOverride[]>([]);
  protected readonly loading = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly success = signal<string | null>(null);
  protected readonly saving = signal(false);
  protected readonly savingMaster = signal(false);

  protected readonly hasOverrides = computed(() => this.overrides().length > 0);

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const [main, master] = await Promise.all([
        this.mailserver.getPostfixOverrides(),
        this.mailserver.getPostfixMasterOverrides(),
      ]);
      this.overrides.set(main);
      this.masterOverrides.set(master);
    } catch {
      this.error.set('Unable to load the Postfix overrides.');
    } finally {
      this.loading.set(false);
    }
  }

  protected addOverride(): void {
    this.overrides.update((list) => [...list, { key: '', value: '' }]);
  }

  protected removeOverride(index: number): void {
    this.overrides.update((list) => list.filter((_, i) => i !== index));
  }

  protected onOverrideKey(index: number, event: Event): void {
    const key = (event.target as HTMLInputElement).value;
    this.overrides.update((list) => list.map((o, i) => (i === index ? { ...o, key } : o)));
  }

  protected onOverrideValue(index: number, event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.overrides.update((list) => list.map((o, i) => (i === index ? { ...o, value } : o)));
  }

  protected async onSave(): Promise<void> {
    this.error.set(null);
    this.success.set(null);
    const cleaned = this.overrides()
      .map((o) => ({ key: o.key.trim(), value: o.value.trim() }))
      .filter((o) => o.key);
    const invalid = cleaned.find((o) => !/^[A-Za-z0-9_]+$/.test(o.key));
    if (invalid) {
      this.error.set(`Invalid Postfix parameter name: "${invalid.key}".`);
      return;
    }
    this.saving.set(true);
    try {
      this.overrides.set(await this.mailserver.setPostfixOverrides(cleaned));
      this.success.set('Postfix overrides saved. Restart the mailserver to apply them.');
    } catch (err) {
      this.error.set(mailserverErrorMessage(err));
    } finally {
      this.saving.set(false);
    }
  }

  protected addMasterOverride(): void {
    this.masterOverrides.update((list) => [...list, { key: '', value: '' }]);
  }

  protected removeMasterOverride(index: number): void {
    this.masterOverrides.update((list) => list.filter((_, i) => i !== index));
  }

  protected onMasterOverrideKey(index: number, event: Event): void {
    const key = (event.target as HTMLInputElement).value;
    this.masterOverrides.update((list) => list.map((o, i) => (i === index ? { ...o, key } : o)));
  }

  protected onMasterOverrideValue(index: number, event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.masterOverrides.update((list) => list.map((o, i) => (i === index ? { ...o, value } : o)));
  }

  protected async onSaveMaster(): Promise<void> {
    this.error.set(null);
    this.success.set(null);
    const cleaned = this.masterOverrides()
      .map((o) => ({ key: o.key.trim(), value: o.value.trim() }))
      .filter((o) => o.key);
    const invalid = cleaned.find((o) => !/^[A-Za-z0-9_.-]+\/[a-z]+\/[A-Za-z0-9_]+$/.test(o.key));
    if (invalid) {
      this.error.set(
        `Invalid master parameter: "${invalid.key}". Expected service/type/parameter.`,
      );
      return;
    }
    this.savingMaster.set(true);
    try {
      this.masterOverrides.set(await this.mailserver.setPostfixMasterOverrides(cleaned));
      this.success.set('Postfix master overrides saved. Restart the mailserver to apply them.');
    } catch (err) {
      this.error.set(mailserverErrorMessage(err));
    } finally {
      this.savingMaster.set(false);
    }
  }
}
