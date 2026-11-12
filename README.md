# ns8-elabftw

A [NethServer 8](https://github.com/NethServer/ns8-core) module that runs
[eLabFTW](https://www.elabftw.net/), the open-source electronic lab notebook:
experiments with versioning and timestamps, a database for chemicals, samples
and equipment, teams, templates, an integrated chemical structure editor
(Ketcher) with substructure search, and exports as PDF/ZIP/ELN archives.

## Architecture

One rootless pod with two containers from pinned official images:

| Container | Image | Purpose |
| --- | --- | --- |
| `elabftw-app` | `ghcr.io/tebbiworld/elabimg` (official `docker.io/elabftw/elabimg` with current Alpine PHP packages, see `elabimg/Containerfile`) | nginx + php-fpm, internal port 8080, published on the node loopback and fronted by Traefik (TLS, Let's Encrypt) |
| `elabftw-db` | `docker.io/library/mysql:8.4` | database, reached on 127.0.0.1 inside the pod |

| Volume | Purpose | Backup |
| --- | --- | --- |
| `elabftw-uploads` | attachments | yes |
| `elabftw-exports` | generated archives and PDFs | yes |
| `elabftw-cache` | PHP/Twig cache | no |
| `elabftw-db` | MySQL data | no — a consistent SQL dump is taken at backup time and imported on restore |

The database schema is installed automatically on the first start
(`AUTO_DB_INIT`) and migrated on module updates (`AUTO_DB_UPDATE`).

## Install

```
add-module ghcr.io/tebbiworld/elabftw:latest 1
```

Then set the host name on the settings page and save. Open
`https://<host>/register.php` — **the first account created becomes the system
administrator.**

## Settings

| Setting | Notes |
| --- | --- |
| Host name | FQDN, used for the Traefik route and as `SITE_URL`. |
| Let's Encrypt / HTTP → HTTPS | as in the other modules |
| Timezone | `PHP_TIMEZONE`/`TZ` |
| Maximum upload size | `MAX_UPLOAD_SIZE` |
| AD/LDAP login | see below |

`SECRET_KEY` is generated once at install time with eLabFTW's own library.
eLabFTW encrypts stored secrets (LDAP bind password, SMTP, timestamping) with
it; a backup restores the original key.

### Active Directory / LDAP

The directory login offers the same chooser as the other tebbiworld modules
(ns8-clamav, ns8-openwebui, ns8-arsnova):

- **User domain of this cluster (recommended).** Only the domain name is
  stored; the module reads the connection from the node's directory proxy
  (`ldapproxy`) together with its service account, so a rotated bind password
  or a moved domain controller is followed automatically (label
  `cluster:accountconsumer`, event `user-domain-changed`). No credentials are
  kept in the module. NS8 can also add an external AD/LDAP as a user domain
  (Domains and users): then it appears here too.
- **LDAP server of its own (advanced).** URL, base DN, bind DN, login
  attribute and the certificate check are entered by hand; the bind password is
  stored in `state/passwords.env` (never in the module environment). `ldaps://`
  and `ldap://` with StartTLS are both supported.

The module writes the resolved connection into eLabFTW's own configuration
through the application's code path, exactly as the sysadmin page would
(`ldap_scheme`/`ldap_host`/`ldap_port`, `ldap_base_dn`, `ldap_username` +
`ldap_password` encrypted with `SECRET_KEY`, `ldap_search_attr`, `ldap_email`,
`ldap_firstname`/`ldap_lastname`, `ldap_use_tls`). Because eLabFTW keeps LDAP in
its own database, the settings are applied once the application is healthy
(`bin/apply-ldap`), not from an environment file at container start. The
certificate check is passed to the image as `LDAP_TLS_REQCERT=demand`/`never`
(the elabimg entrypoint renders `/run/openldap/ldap.conf` from it); it defaults
to on for a server of its own with TLS, and can be turned off for the
self-signed certificates of Samba AD and internal CAs.

**How the container reaches the directory.** For a user domain the app
container talks clear LDAP to the proxy on the node loopback, reached through
`pasta --map-host-loopback 169.254.1.3` (written to the module user's
`containers.conf` only while a user domain is in use; changing it restarts the
pod so the new rootless network picks it up). For a server of its own that
resolves to this node, the container uses `host.containers.internal`
(`bin/ldap-container-host`).

LDAP users log in with their directory account on the normal login page and
choose their team on first login; their account is created on the fly (name
and e-mail from the directory). The very first account of the instance —
registered locally or created by an LDAP login — becomes the system
administrator; every later account waits for validation by an admin (eLabFTW
default). Team synchronisation from a directory attribute and further options
remain available in the sysadmin panel.

**No group restriction.** eLabFTW has no user search filter, so a login cannot
be limited to a group, and the NS8 accounts that a domain hides from clients
(for example `krbtgt`, the proxy's own service account) are not filtered out
either: anyone with a valid directory account and the login attribute can sign
in (subject to eLabFTW's admin validation of new accounts). Restrict access
with eLabFTW's own means (admin validation, team membership) or front the
instance accordingly. The group field is therefore not shown for this module.

### Timestamping (RFC 3161)

eLabFTW can timestamp experiments with an external timestamp authority
(sysadmin panel → Timestamping). The [TSA module](https://github.com/tebbiworld/ns8-tsa)
of this repository provides one on the cluster.

## Backup and restore

`module-dump-state` writes `state/elabftw.sql` with `mysqldump
--single-transaction` before every backup; `state-include.conf` includes the
state, the dump, uploads and exports. On restore the module imports the dump
into a fresh database volume (MySQL first-start import), copies settings and
secrets from the backed-up environment and re-runs its configuration.

## Notes

* `update-module` restarts the pod; the new eLabFTW version migrates the schema.
* `runagent -m elabftw1 podman logs elabftw-app` shows the application log.
* eLabFTW is licensed AGPL-3.0; the images are pulled at runtime and not
  redistributed. The module's own code is GPL-3.0-or-later.
