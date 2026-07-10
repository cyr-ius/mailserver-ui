import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';

import { MailserverService } from '../../../core/mailserver.service';
import { RspamdCommand, RspamdCommandKind } from '../../../core/mailserver.models';
import { mailserverErrorMessage } from '../mailserver.utils';

/** Which arguments a directive takes, and how to label them in the table. */
interface KindDescriptor {
  kind: RspamdCommandKind;
  /** What the directive writes into, shown as a hint under the table. */
  hint: string;
  target?: { label: string; placeholder: string };
  option?: { placeholder: string };
  value?: { placeholder: string };
}

const KINDS: readonly KindDescriptor[] = [
  {
    kind: 'set-common-option',
    hint: 'options.inc',
    option: { placeholder: 'dns' },
    value: { placeholder: '{ nameserver = ["127.0.0.11"]; }' },
  },
  {
    kind: 'set-option-for-controller',
    hint: 'worker-controller.inc',
    option: { placeholder: 'password' },
    value: { placeholder: '$2$abc…' },
  },
  {
    kind: 'set-option-for-proxy',
    hint: 'worker-proxy.inc',
    option: { placeholder: 'timeout' },
    value: { placeholder: '30s' },
  },
  {
    kind: 'enable-module',
    hint: '<module>.conf',
    target: { label: 'Module', placeholder: 'dkim_signing' },
  },
  {
    kind: 'disable-module',
    hint: '<module>.conf',
    target: { label: 'Module', placeholder: 'clickhouse' },
  },
  {
    kind: 'set-option-for-module',
    hint: '<module>.conf',
    target: { label: 'Module', placeholder: 'milter_headers' },
    option: { placeholder: 'extended_spam_headers' },
    value: { placeholder: 'true' },
  },
  {
    kind: 'add-line',
    hint: '<file>, verbatim',
    target: { label: 'File', placeholder: 'logging.inc' },
    value: { placeholder: 'level = "silly";' },
  },
];

/** An Rspamd module or option name, and an override file name. */
const NAME_RE = /^[A-Za-z0-9_-]+$/;
const FILENAME_RE = /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/;

/** An empty command of the given kind, ready to be filled in. */
function emptyCommand(kind: RspamdCommandKind): RspamdCommand {
  return { kind, target: '', option: '', value: '' };
}

/** The simplified Rspamd overrides of rspamd/custom-commands.conf. */
@Component({
  selector: 'app-mailserver-rspamd',
  templateUrl: './rspamd.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Rspamd {
  private readonly mailserver = inject(MailserverService);

  protected readonly kinds = KINDS;
  protected readonly commands = signal<RspamdCommand[]>([]);
  protected readonly rspamdEnabled = signal(true);
  protected readonly loading = signal(false);
  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly success = signal<string | null>(null);

  protected readonly hasCommands = computed(() => this.commands().length > 0);

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const overrides = await this.mailserver.getRspamdOverrides();
      this.commands.set(overrides.commands);
      this.rspamdEnabled.set(overrides.rspamd_enabled);
    } catch (err) {
      this.error.set(mailserverErrorMessage(err));
    } finally {
      this.loading.set(false);
    }
  }

  /** The descriptor of a command's kind; KINDS always holds every kind. */
  protected descriptor(command: RspamdCommand): KindDescriptor {
    return KINDS.find((entry) => entry.kind === command.kind) ?? KINDS[0];
  }

  protected addCommand(): void {
    this.commands.update((list) => [...list, emptyCommand('set-option-for-module')]);
  }

  protected removeCommand(index: number): void {
    this.commands.update((list) => list.filter((_, i) => i !== index));
  }

  /** Change a row's directive, clearing the arguments the new one does not take. */
  protected onKind(index: number, event: Event): void {
    const kind = (event.target as HTMLSelectElement).value as RspamdCommandKind;
    this.commands.update((list) => list.map((c, i) => (i === index ? emptyCommand(kind) : c)));
  }

  protected onField(index: number, field: 'target' | 'option' | 'value', event: Event): void {
    const text = (event.target as HTMLInputElement).value;
    this.commands.update((list) => list.map((c, i) => (i === index ? { ...c, [field]: text } : c)));
  }

  /** Return the first reason a command would be rejected, or null when valid. */
  private invalidReason(command: RspamdCommand): string | null {
    const descriptor = this.descriptor(command);
    if (descriptor.target && !command.target) {
      return `${command.kind} requires a ${descriptor.target.label.toLowerCase()}.`;
    }
    if (descriptor.option && !command.option) {
      return `${command.kind} requires an option name.`;
    }
    if (descriptor.value && !command.value) {
      return `${command.kind} requires a value.`;
    }
    if (command.option && !NAME_RE.test(command.option)) {
      return `Invalid Rspamd option name: "${command.option}".`;
    }
    if (command.target) {
      const pattern = command.kind === 'add-line' ? FILENAME_RE : NAME_RE;
      if (!pattern.test(command.target)) {
        const noun = command.kind === 'add-line' ? 'override file name' : 'module name';
        return `Invalid Rspamd ${noun}: "${command.target}".`;
      }
    }
    return null;
  }

  protected async onSave(): Promise<void> {
    this.error.set(null);
    this.success.set(null);

    const cleaned = this.commands().map((command) => ({
      ...command,
      target: command.target.trim(),
      option: command.option.trim(),
      value: command.value.trim(),
    }));
    for (const command of cleaned) {
      const reason = this.invalidReason(command);
      if (reason) {
        this.error.set(reason);
        return;
      }
    }

    this.saving.set(true);
    try {
      this.commands.set((await this.mailserver.setRspamdOverrides(cleaned)).commands);
      this.success.set('Rspamd commands saved. Restart the mailserver to apply them.');
    } catch (err) {
      this.error.set(mailserverErrorMessage(err));
    } finally {
      this.saving.set(false);
    }
  }
}
