#
# Copyright (C) 2026 tebbi
# SPDX-License-Identifier: GPL-3.0-or-later
#

"""eLabFTW side of the shared directory login (pypkg/ldapsettings.py).

ldapsettings.py stores the settings exactly as in ns8-clamav,
ns8-idevice-backup, ns8-openwebui and ns8-arsnova (a user domain of this
cluster, or an LDAP server of its own). eLabFTW binds the directory itself and
keeps the connection in its OWN database (the `config` table), written through
the application's Config class so the bind password is encrypted with
SECRET_KEY exactly as the sysadmin page would do it. This module turns the
stored settings into that `config` patch (see bin/apply-ldap).

How eLabFTW reaches the directory:
  user domain   through the node's ldapproxy, which listens on the node
                loopback in clear LDAP (it talks TLS to the domain controllers
                itself). Containers on the default rootless network (pasta)
                cannot reach the node loopback, so the module user's pasta maps
                it to LOOPBACK_ALIAS (~/.config/containers/containers.conf,
                written only while a user domain is in use), exactly as the
                ARSnova module does.
  own server    directly, via bin/ldap-container-host (a host name that
                resolves to this node is reached through host.containers.internal).

Differences from the other modules:
  * eLabFTW has NO user search filter, so a group restriction cannot be
    enforced (neither can the hidden-account filter krbtgt/ldapservice). The
    group field is therefore hidden in the UI (LdapLogin showGroup=false) and
    ldap_group is ignored here. Documented in the README.
  * eLabFTW fully supports StartTLS (ldap_use_tls=1 with scheme ldap), so a
    custom ldap:// server with StartTLS is accepted (not refused like Open
    WebUI / ARSnova).
"""

import json
import os
import subprocess
import sys
import time
import urllib.parse
import urllib.request

import agent
import ldapsettings

# address under which the containers reach the node loopback (pasta
# --map-host-loopback); podman itself uses 169.254.1.1 (DNS) and
# 169.254.1.2 (host.containers.internal)
LOOPBACK_ALIAS = "169.254.1.3"
CONTAINERS_CONF = os.path.expanduser("~/.config/containers/containers.conf")
CONTAINERS_CONF_HEADER = "# Written by the eLabFTW module (pypkg/elabftwldap.py). Do not edit by hand.\n"
# Shared directory fields that end up in eLabFTW's config / ldap.conf; reject
# control characters so a value cannot smuggle extra content in. The module's
# own mail/name attributes are already constrained by the input JSON schema.
_STRING_FIELDS = ("ldap_domain", "ldap_url", "ldap_base_dn", "ldap_bind_dn",
                  "ldap_user_attribute")


def _log(msg, level=agent.SD_WARNING):
    print(level + msg, file=sys.stderr)


def enabled(env=None):
    """LDAP_ENABLED: the module uses a directory login at all."""
    env = os.environ if env is None else env
    return (env.get("LDAP_ENABLED") or "").strip().lower() in ("1", "true")


# --- migration (pre-1.3.0 custom-only layout) ----------------------------------

# Derived values the new code recomputes from LDAP_URL; dropped on migration.
STALE_LEGACY_KEYS = ("LDAP_HOST", "LDAP_PORT", "LDAP_SCHEME", "LDAP_CONTAINER_HOST", "LDAP_VALIDATE_CERT")


def legacy_updates(env):
    """Environment changes for settings written before 1.3.0, when only an LDAP
    server entered by hand existed: carry it over as a custom server with its
    previous behaviour (schema ad, no StartTLS, certificate check from the old
    LDAP_VALIDATE_CERT). Returns {} when there is nothing to migrate (already on
    the new layout, or the instance never used LDAP). Used by the update hook
    and by restore-module when a pre-1.3.0 backup is restored."""
    if env.get("LDAP_SOURCE"):
        return {}
    if not (env.get("LDAP_URL") or env.get("LDAP_ENABLED")):
        return {}
    return {
        "LDAP_SOURCE": "custom",
        "LDAP_SCHEMA": "ad",
        "LDAP_START_TLS": "false",
        "LDAP_TLS_VERIFY": "true" if (env.get("LDAP_VALIDATE_CERT", "false").strip().lower() in ("1", "true")) else "false",
        # older versions stored the flag as a Python bool string ("True"/"False")
        "LDAP_ENABLED": "true" if (env.get("LDAP_ENABLED", "false").strip().lower() in ("1", "true")) else "false",
    }


# --- validation ----------------------------------------------------------------

def validate(data, active):
    """eLabFTW limits on top of ldapsettings.validate(): list of (field, error).

    The values are written into eLabFTW's config (and, for the certificate
    check, into ldap.conf): a control character would break those files, so it
    is refused. eLabFTW supports StartTLS, so (unlike Open WebUI / ARSnova) a
    custom ldap:// server with StartTLS is NOT refused here.
    """
    errors = []
    for field in _STRING_FIELDS:
        value = data.get(field)
        if isinstance(value, str) and any(ord(c) < 32 for c in value):
            errors.append((field, "ldap_value_invalid"))
    return errors


# --- node loopback for the user domain ---------------------------------------------

def needs_host_loopback():
    """The app container must reach the node loopback: ldapproxy of a user domain."""
    return (enabled() and os.environ.get("LDAP_SOURCE", "domain") == "domain"
            and bool(os.environ.get("LDAP_DOMAIN")))


def configure_host_loopback():
    """Write or remove the pasta loopback mapping of the module user. Return
    True when it changed: the rootless network is then recreated only after
    every container of the module stopped (see configure-module/80start_services)."""
    wanted = None
    if needs_host_loopback():
        wanted = CONTAINERS_CONF_HEADER + (
            "# eLabFTW reaches the node's ldapproxy (user domain login) at\n"
            f"# {LOOPBACK_ALIAS}; see the module README.\n"
            "[network]\n"
            f'pasta_options = ["--map-host-loopback", "{LOOPBACK_ALIAS}"]\n')
    try:
        with open(CONTAINERS_CONF) as fp:
            current = fp.read()
    except FileNotFoundError:
        current = None
    if current == wanted:
        return False
    if current is not None and not current.startswith(CONTAINERS_CONF_HEADER):
        # not written by the module: leave it alone (a user domain login then
        # stays off, apply-ldap logs that the loopback is not mapped)
        _log(f"{CONTAINERS_CONF} was not written by the module: left unchanged")
        return False
    if wanted is None:
        os.unlink(CONTAINERS_CONF)
    else:
        os.makedirs(os.path.dirname(CONTAINERS_CONF), exist_ok=True)
        with open(CONTAINERS_CONF + ".tmp", "w") as fp:
            fp.write(wanted)
        os.replace(CONTAINERS_CONF + ".tmp", CONTAINERS_CONF)
    return True


def host_loopback_active():
    """The running rootless network maps the node loopback (pasta option)."""
    try:
        out = subprocess.run(["pgrep", "-u", str(os.getuid()), "-a", "pasta"],
                             capture_output=True, text=True).stdout
    except OSError:
        return False
    return any("rootless-netns" in line and f"--map-host-loopback {LOOPBACK_ALIAS}" in line
               for line in out.splitlines())


def _container_host(host):
    """Host name the *app container* must use to reach a server of its own
    (bin/ldap-container-host: a name that resolves to this node is reached
    through host.containers.internal). The user domain uses LOOPBACK_ALIAS and
    never passes through here."""
    if not host:
        return host
    try:
        mapped = subprocess.run(
            [os.path.expanduser("~/.config/bin/ldap-container-host"), host],
            capture_output=True, text=True, check=True).stdout.strip()
        return mapped or host
    except (OSError, subprocess.CalledProcessError) as exc:
        _log(f"ldap-container-host failed for {host}: {exc}; using the name unchanged")
        return host


# --- eLabFTW config patch ---------------------------------------------------------

def tls_reqcert():
    """Value for /etc/openldap/ldap.conf (mounted into the app container):
    'demand' verifies the server certificate, 'never' accepts a self-signed
    one. Only meaningful for a TLS connection of a server of its own; the
    user domain talks clear LDAP to the loopback proxy."""
    if os.environ.get("LDAP_SOURCE", "domain") != "custom":
        return "never"
    url = urllib.parse.urlparse(os.environ.get("LDAP_URL", ""))
    tls = url.scheme == "ldaps" or os.environ.get("LDAP_START_TLS") == "true"
    if not tls:
        return "never"
    return "demand" if os.environ.get("LDAP_TLS_VERIFY", "true") != "false" else "never"


def resolved_params():
    """The eLabFTW `config` patch for the current settings, or None when the
    directory login is off or the directory is not available (fail secure: the
    caller then switches ldap_toggle off, local accounts keep working).

    The connection (user domain through the node's ldapproxy, or a server of
    its own) is resolved 1:1 by ldapsettings.env_lines(), so the loopback/bind
    handling stays identical to the other modules.
    """
    if not enabled():
        return None
    kv = {}
    for line in ldapsettings.env_lines(active=True):
        if "=" in line:
            key, value = line.split("=", 1)
            kv[key] = value
    if not kv.get("LDAP_HOST"):
        # domain source whose user domain is currently unavailable: fail secure
        return None

    source = kv.get("LDAP_SOURCE", "domain")
    tls = kv.get("LDAP_TLS", "none")  # none | starttls | ssl
    schema = kv.get("LDAP_SCHEMA", "ad")
    attribute = kv.get("LDAP_USER_ATTRIBUTE") or ("uid" if schema == "rfc2307" else "sAMAccountName")

    if source == "domain":
        if not host_loopback_active():
            _log("the rootless network does not map the node loopback yet: save the settings again "
                 "(configure-module restarts the whole module)")
            return None
        host, scheme, use_tls = LOOPBACK_ALIAS, "ldap", "0"
    else:
        host = _container_host(kv["LDAP_HOST"])
        scheme = "ldaps" if tls == "ssl" else "ldap"
        use_tls = "1" if tls == "starttls" else "0"

    params = {
        "ldap_toggle": "1",
        "ldap_scheme": scheme,
        "ldap_host": host,
        "ldap_port": kv.get("LDAP_PORT", "389"),
        "ldap_base_dn": kv.get("LDAP_BASE_DN", ""),
        "ldap_username": kv.get("LDAP_BIND_DN", ""),
        "ldap_password": kv.get("LDAP_BIND_PASSWORD", ""),
        "ldap_search_attr": attribute,
        "ldap_email": os.environ.get("LDAP_MAIL_ATTRIBUTE", "mail") or "mail",
        "ldap_firstname": os.environ.get("LDAP_FIRSTNAME_ATTRIBUTE", "givenName") or "givenName",
        "ldap_lastname": os.environ.get("LDAP_LASTNAME_ATTRIBUTE", "sn") or "sn",
        "ldap_use_tls": use_tls,
    }
    return params


# --- applying the settings to the running application --------------------------

# php that reads the config patch from STDIN and applies it through eLabFTW's
# own Config class, so the bind password is encrypted with SECRET_KEY exactly as
# the sysadmin page would do it.
_PATCH_PHP = r'''
require "/elabftw/vendor/autoload.php";
$params = json_decode(stream_get_contents(STDIN), true);
$config = \Elabftw\Models\Config::getConfig();
$config->patch(\Elabftw\Enums\Action::Update, $params);
echo "ldap config applied\n";
'''


def _wait_healthy(timeout_steps=120, step=5):
    port = os.environ["WEB_PORT"]
    for _ in range(timeout_steps):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthcheck", timeout=5) as r:
                if 200 <= r.status < 300:  # nginx answers 204
                    return True
        except Exception:
            pass
        time.sleep(step)
    return False


def apply_to_app():
    """Write the current directory-login settings into eLabFTW's own config,
    once the application (and therefore the database schema) is up. Any problem
    leaves the directory login off (ldap_toggle=0, fail secure). Raises on a
    health timeout or a failing config patch. Shared by
    configure-module/85configure_ldap and events/user-domain-changed."""
    if not _wait_healthy():
        raise TimeoutError("eLabFTW did not become healthy in time; LDAP settings not applied")

    params = resolved_params()
    if params is None:
        params = {"ldap_toggle": "0"}
        _log("directory login off in eLabFTW (disabled or directory unavailable)", agent.SD_NOTICE)
    else:
        _log(f"applying directory login: {params['ldap_scheme']}://{params['ldap_host']}:{params['ldap_port']}", agent.SD_INFO)

    subprocess.run(["podman", "exec", "-i", "elabftw-app", "php", "-r", _PATCH_PHP],
                   input=json.dumps(params), text=True, check=True, stdout=sys.stderr)
