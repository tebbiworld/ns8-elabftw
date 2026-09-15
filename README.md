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
| `elabftw-app` | `docker.io/elabftw/elabimg` | nginx + php-fpm, internal port 8080, published on the node loopback and fronted by Traefik (TLS, Let's Encrypt) |
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

The module writes the directory settings into eLabFTW's configuration through
the application's own code path, exactly as the sysadmin page would:

| Setting | eLabFTW key |
| --- | --- |
| LDAP URL | `ldap_scheme`, `ldap_host`, `ldap_port` |
| Search base DN | `ldap_base_dn` |
| Bind DN / password | `ldap_username`, `ldap_password` (encrypted with `SECRET_KEY`) |
| Login attribute | `ldap_search_attr` — `sAMAccountName` for AD, `uid` for OpenLDAP, comma-separated list allowed |
| Mail attribute | `ldap_email` — eLabFTW requires an e-mail per user; on AD with empty `mail` use `userPrincipalName` |
| First/last name | `ldap_firstname`, `ldap_lastname` |
| Validate LDAPS certificate | `TLS_REQCERT demand`/`never` in a module-managed `ldap.conf` mounted into the container (off by default: Samba AD and internal CAs use self-signed certificates) |

LDAP users log in with their directory account on the normal login page and
choose their team on first login; their account is created on the fly (name
and e-mail from the directory). The very first account of the instance —
registered locally or created by an LDAP login — becomes the system
administrator; every later account waits for validation by an admin (eLabFTW
default). Team synchronisation from a directory attribute and further options
remain available in the sysadmin panel.

If the directory server is this very node (NS8 Samba account provider), the
container reaches it through `host.containers.internal` — handled
automatically (`bin/ldap-container-host`).

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
