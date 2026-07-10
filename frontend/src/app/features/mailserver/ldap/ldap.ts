import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';

import { MailserverService } from '../../../core/mailserver.service';
import { LdapScope } from '../../../core/mailserver.models';
import { mailserverErrorMessage } from '../mailserver.utils';

/** What each Postfix LDAP map answers, keyed by its scope. */
interface ScopeDescriptor {
  scope: LdapScope;
  label: string;
  filename: string;
  /** The lookup Postfix performs against this map. */
  purpose: string;
  placeholder: string;
}

const SCOPES: readonly ScopeDescriptor[] = [
  {
    scope: 'users',
    label: 'Users',
    filename: 'ldap-users.cf',
    purpose: 'virtual_mailbox_maps — which addresses are mailboxes',
    placeholder:
      'server_host = mail.example.com\nsearch_base = ou=people,dc=example,dc=com\nquery_filter = (&(mail=%s)(mailEnabled=TRUE))\nresult_attribute = mail\nbind = yes\nbind_dn = cn=admin,dc=example,dc=com\nbind_pw = secret\nversion = 3',
  },
  {
    scope: 'groups',
    label: 'Groups',
    filename: 'ldap-groups.cf',
    purpose: 'virtual_alias_maps — distribution groups',
    placeholder:
      'server_host = mail.example.com\nsearch_base = ou=groups,dc=example,dc=com\nquery_filter = (&(mailGroupMember=%s))\nresult_attribute = mail\nversion = 3',
  },
  {
    scope: 'aliases',
    label: 'Aliases',
    filename: 'ldap-aliases.cf',
    purpose: 'virtual_alias_maps — one address forwarding to another',
    placeholder:
      'server_host = mail.example.com\nsearch_base = ou=people,dc=example,dc=com\nquery_filter = (&(mailAlias=%s))\nresult_attribute = mail\nversion = 3',
  },
  {
    scope: 'domains',
    label: 'Domains',
    filename: 'ldap-domains.cf',
    purpose: 'virtual_mailbox_domains — which domains are hosted',
    placeholder:
      'server_host = mail.example.com\nsearch_base = dc=example,dc=com\nquery_filter = (|(mail=*@%s)(mailAlias=*@%s))\nresult_attribute = mail\nversion = 3',
  },
];

/** The Postfix LDAP maps read when ACCOUNT_PROVISIONER=LDAP. */
@Component({
  selector: 'app-mailserver-ldap',
  templateUrl: './ldap.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class Ldap {
  private readonly mailserver = inject(MailserverService);

  protected readonly scopes = SCOPES;
  protected readonly scope = signal<LdapScope>('users');
  protected readonly content = signal('');
  protected readonly configured = signal(false);
  protected readonly provisioner = signal('');
  protected readonly ldapEnabled = signal(true);
  protected readonly overriddenKeys = signal<string[]>([]);
  protected readonly loading = signal(false);
  protected readonly saving = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly success = signal<string | null>(null);

  /** The descriptor of the map currently open; SCOPES always holds the scope. */
  protected readonly current = computed(
    () => SCOPES.find((entry) => entry.scope === this.scope()) ?? SCOPES[0],
  );

  /** The overridden keys as one run of text, so the commas do not drift apart. */
  protected readonly overriddenList = computed(() => this.overriddenKeys().join(', '));

  constructor() {
    void this.load();
  }

  private async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const config = await this.mailserver.getLdapConfig(this.scope());
      this.content.set(config.content);
      this.configured.set(config.configured);
      this.provisioner.set(config.provisioner);
      this.ldapEnabled.set(config.ldap_enabled);
      this.overriddenKeys.set(config.overridden_keys);
    } catch (err) {
      this.error.set(mailserverErrorMessage(err));
    } finally {
      this.loading.set(false);
    }
  }

  protected setScope(scope: LdapScope): void {
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
      const config = await this.mailserver.setLdapConfig(this.scope(), this.content());
      this.content.set(config.content);
      this.configured.set(config.configured);
      this.overriddenKeys.set(config.overridden_keys);
      this.success.set(
        config.configured
          ? `${this.current().filename} was saved. Restart the mailserver to apply it.`
          : `${this.current().filename} was removed; docker-mailserver falls back to its default map.`,
      );
    } catch (err) {
      this.error.set(mailserverErrorMessage(err));
    } finally {
      this.saving.set(false);
    }
  }
}
