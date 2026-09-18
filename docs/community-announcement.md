<!--
First community post for the NS8 eLabFTW module, written in the style
of https://community.nethserver.org/t/ns8-forgejo-testing/28554 (first post).
Paste into a new topic on community.nethserver.org, category "App", tag "ns8".
Fill in the wiki link once the page is published.
-->

# NS8 eLabFTW (testing)

Hi all,

I've built an NS8 module for [eLabFTW](https://www.elabftw.net/) — the open-source electronic lab notebook (ELN) for keeping experiments, protocols and a lab inventory in one place.

It's in my community repository. To try it, add the repo once:

```
api-cli run add-repository --data '{"name":"tebbiworld","url":"https://raw.githubusercontent.com/tebbiworld/ns8-repo/main/ns8/updates/","status":true,"testing":false}'
```

then install **eLabFTW** from the Software Center. (Or straight from the image: `add-module ghcr.io/tebbiworld/elabftw:latest 1`.)

What it does:

* Runs the official `elabftw/elabimg` image (nginx + php-fpm) with MySQL 8.4 in one rootless pod, published on one host name through Traefik with Let's Encrypt
* Experiments with versioning and timestamps, plus a database for chemicals, samples and equipment, teams and templates
* An integrated chemical structure editor (Ketcher) with substructure search, and exports as PDF, ZIP or ELN archives
* **Active Directory / LDAP login** configured from the module settings — written into eLabFTW's own configuration, with the bind password encrypted exactly as the sysadmin page does it
* Optional RFC 3161 experiment timestamping against an external timestamp authority (my [TSA module](https://github.com/tebbiworld/ns8-tsa) can serve as one)
* NS8 backup with a consistent SQL dump plus uploads and exports; the restore rebuilds the database from the dump

A few things to know:

* **The first account created — whether registered locally or via an LDAP login — becomes the system administrator.** Every later account waits for admin validation (eLabFTW's own default).
* You need a host name (FQDN) that resolves to the node for the Traefik route and Let's Encrypt certificate.
* LDAP/AD is optional; self-signed certificates (Samba AD, internal CAs) are accepted, and if the directory server is the node itself the container reaches it automatically via `host.containers.internal`.
* The schema is installed on first start and migrated automatically on module updates.

It's early days, so I'd really appreciate anyone giving it a spin and telling me what breaks or feels off — especially around the AD/LDAP side.

Docs: NethServer wiki (tebbiworld repository) · Source: [github.com/tebbiworld/ns8-elabftw](https://github.com/tebbiworld/ns8-elabftw)

Thanks!

*Category: App · Tags: ns8*
