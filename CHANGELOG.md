# Changelog

## 1.3.0 — unreleased

### Added

- **Directory login chooser "user domain of this cluster" OR "LDAP server of its
  own"**, the shared building block of the other tebbiworld modules
  (`pypkg/ldapsettings.py`, `ui/src/components/LdapLogin.vue`, identical to
  ns8-clamav / ns8-openwebui / ns8-arsnova). A user domain stores only its name
  and reads the connection from the node's `ldapproxy` and its service account,
  so a rotated bind password or a moved domain controller is followed
  automatically (label `cluster:accountconsumer`, event `user-domain-changed`);
  no credentials are kept in the module. The previous "LDAP server entered by
  hand" is the second option and is unchanged in behaviour.

### Changed

- eLabFTW keeps the LDAP connection in its own database, so the resolved
  settings are written through the application once it is healthy
  (`bin/apply-ldap`, shared by `configure-module` and the `user-domain-changed`
  event) instead of being derived from `LDAP_URL` at configure time. StartTLS on
  an `ldap://` server is now supported (`ldap_use_tls`).
- For a user domain the app container reaches the proxy on the node loopback
  through `pasta --map-host-loopback 169.254.1.3` (written to the module user's
  `containers.conf` only while a user domain is in use).

### Migration

- An instance configured before 1.3.0 is carried over as a custom LDAP server
  with its previous settings (schema `ad`, no StartTLS, certificate check from
  the former "Validate LDAPS certificate"), so its login keeps working; the
  bind password stays in `state/passwords.env`. The same applies when a
  pre-1.3.0 backup is restored.

### Notes

- eLabFTW has no user search filter: a login cannot be limited to a group (and
  the accounts a domain hides from clients are not filtered out). The group
  field is not shown for this module; restrict access with eLabFTW's admin
  validation of new accounts. See the README.

## 1.2.0 — 2026-10-21

### Security

- **PHP 8.4.27** (fix of CVE-2026-109618/109619, remote code execution in PHP, CVSS 9.2). The published eLabFTW images (6.0.1 to the nightly build of 2026-10-21) still run PHP 8.4.25/8.4.26, so the module now runs `ghcr.io/tebbiworld/elabimg:6.0.1-php8.4.27`: the official `elabftw/elabimg:6.0.1` with the PHP packages of its Alpine release (3.24) upgraded, built by `build-images.sh` from `elabimg/Containerfile`. eLabFTW stays at 6.0.1; the build refuses an image whose PHP CLI or php-fpm is not the pinned version. The automatic upstream update keeps working on the `elabftw/elabimg` pin and rebuilds the derived image for each new eLabFTW release.
- **PHP session upload progress turned off** (`session.upload_progress.enabled = 0`), the configuration mitigation the advisory names for its session lifecycle case; eLabFTW upstream does the same in its next image. eLabFTW does not use the feature. It stays in place as defence in depth.

## 1.1.0 — 2026-09-19

Alignment with the NethServer module conventions (NethServer/agents skills).

### Changed

- **Secrets moved out of the module environment.** `SECRET_KEY`, the MySQL passwords and the LDAP bind password are now kept in `state/passwords.env` (mode 0600) instead of `state/environment`, which NS8 mirrors to Redis in plain text. Existing installations are migrated on update; the values do not change. The generated `elabftw.env` is private (0600), and the secrets are no longer passed on the podman command line or embedded in the container health check.
- The module backup now includes `state/passwords.env`; restore reads the secrets from it (backups taken with 1.0.0 are still restorable) and re-creates the route with the original Let's Encrypt setting.
- MySQL pinned to `8.4.10` instead of the rolling `8.4` tag.
- Service restarts list every unit of the pod explicitly.

### Added

- Robot Framework tests (install, update from the previous release, backup and restore) run on real NS8 nodes through `stephdl/ns8-ci-actions`.

### Platform integration

- **Clone and move.** New `clone-module` step (a link to the restore step): a cloned or moved instance gets its route and settings back instead of coming up unconfigured. The settings are read from the source instance, including those a new instance starts with a default for.
- `org.nethserver.volumes`: the bulk-data volume(s) `elabftw-uploads elabftw-exports` can be placed on an additional disk when the module is installed.
- Release notes are linked from the software centre (`relnotes_url`).

## 1.0.0 — 2026-09-15

- Initial release: eLabFTW from the official image (pinned) with MySQL 8.4 in
  one pod, Traefik route, AD/LDAP login configured through eLabFTW's own
  Config class (encrypted bind password), automatic schema install/update,
  backup with SQL dump + uploads/exports and restore, settings UI (EN/DE).
