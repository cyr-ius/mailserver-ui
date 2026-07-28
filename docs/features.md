# Features

- **Local authentication** — a default admin is seeded on first startup
  (random password printed once to the logs).
- **OIDC / SSO** — Keycloak, Authentik, etc. **Configured entirely from the web
  UI** (Settings → OIDC / SSO) and stored in the database. No redeploy needed to
  change the SSO configuration.
- **User management** — list local & OIDC accounts, create and delete local ones,
  deactivate any of them (a deactivated account keeps its data but can no longer
  sign in, and its sessions and tokens stop working at once), reset local
  passwords (admin only), personal access tokens issued from the profile page. The
  last active administrator can neither be deleted nor deactivated, and an OIDC
  identity can never take over a local account of the same name.
- **Audit log** — every sign-in, sign-out, account change, settings change and
  token operation is appended to an immutable trail, browsable under
  Settings → Audit log with filters on the actor, the category and the outcome.
- **Mail connector** — an SMTP server configured from the web UI (Settings → Mail
  connector), notifying on sign-in/sign-out alone or on every audit event, with a
  test button to check the configuration.
- **Mailbox management** — create, reset the password of, and delete
  docker-mailserver accounts, with per-mailbox quotas.
- **Mailserver administration** — aliases (system & regex), relay hosts and
  exclusions, DKIM keys, DNS records, Postfix/Dovecot overrides, Sieve scripts,
  custom SpamAssassin rules and Postgrey whitelists, Rspamd overrides, Postfix
  LDAP maps, TLS certificates, access restrictions, Dovecot master accounts and
  mail queue actions.
- **Dashboard** — real mailbox disk usage (from Dovecot, not the configured
  quota), TLS certificate expiry, DKIM coverage per hosted domain, supervised
  service health, the mail queue backlog, banned IPs per jail, the spam/virus and
  delivery counters of the last 24 hours, and any contradiction between the
  mailserver's environment variables.
- **Fail2ban** — inspect jails, ban and unban IPs, read the fail2ban log.
- **Disabled features are called out** — docker-mailserver only reads a config
  file when the matching `ENABLE_*` toggle is on. Pages guarded by a toggle that
  is off (quotas, fail2ban, SpamAssassin, Postgrey, Amavis) say so, instead of
  silently saving a file nothing will ever read.
- Group-based role mapping and optional group-restricted access for OIDC users.
