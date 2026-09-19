# Changelog

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
