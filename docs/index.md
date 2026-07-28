# Docker Mailserver UI

A web interface for [docker-mailserver](https://github.com/docker-mailserver/docker-mailserver).
Single container serving an Angular SPA and a FastAPI backend, with local and
OIDC/SSO authentication.

| Layer    | Tech                                       |
| -------- | ------------------------------------------ |
| Frontend | Angular 22 (signals, zoneless, standalone) |
| Backend  | FastAPI 0.139 (async, Pydantic v2)         |
| Database | SQLite via SQLModel                        |
| UI       | Bootstrap 5.3 / Bootstrap Icons            |
| Runtimes | Python 3.14 / Node.js 18+                  |

## How it talks to docker-mailserver

Everything — mailboxes, aliases, relays, DKIM, mail log, queue, fail2ban — is
driven **through the Docker socket** with `docker exec` inside the mailserver
container. Config files are read and written there directly; **no config
directory is bind-mounted** into the UI container.

This means:

- `/var/run/docker.sock` **must** be mounted into the `mailserver-ui` container;
- `MAILSERVER_CONTAINER` must name the docker-mailserver container;
- mounting the Docker socket grants the container root-equivalent control of the
  host — only enable it if you accept that risk. Mount it read-only (`:ro`).

Mailbox management requires the mailserver to run with
`ACCOUNT_PROVISIONER=FILE`, because the UI edits `postfix-accounts.cf` and
`dovecot-quotas.cf`, which only the FILE provisioner reads.

See [Architecture](architecture.md) for the full picture, [Installation](getting-started/installation.md)
to get running, and [Features](features.md) for the tour of what the UI can do.

## License

MIT — see the [repository](https://github.com/cyr-ius/mailserver-ui) for details.
