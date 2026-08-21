# -*- coding: utf-8 -*-
"""Access to the add-on settings.

Every setting lives in ``plone.app.registry`` (editable in the control panel)
but can be overridden by an environment variable named
``MAITUX_OAUTH2_<FIELDNAME>``.  The environment always wins, which keeps
secrets out of the ZODB when the container is configured through
docker-compose.
"""

import os

from plone.registry.interfaces import IRegistry
from zope.component import queryUtility
from zope.schema import Bool
from zope.schema import Int
from zope.schema import List
from zope.schema import Text
from zope.schema import TextLine
from zope.schema import getFieldsInOrder

from maitux.oauth2 import logger
from maitux.oauth2.interfaces import IOAuth2Settings

PREFIX = "maitux.oauth2"
ENV_PREFIX = "MAITUX_OAUTH2_"

TRUTHY = ("1", "true", "yes", "on", "y", "t")
FALSY = ("0", "false", "no", "off", "n", "f", "")

FIELDS = dict(getFieldsInOrder(IOAuth2Settings))

_marker = object()


def _to_unicode(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def _coerce(name, raw):
    """Turn an environment string into the type declared by the schema."""
    field = FIELDS.get(name)
    raw = _to_unicode(raw)
    if isinstance(field, Bool):
        return raw.strip().lower() in TRUTHY
    if isinstance(field, Int):
        try:
            return int(raw.strip())
        except (TypeError, ValueError):
            logger.warning("Bad integer in %s%s: %r", ENV_PREFIX, name.upper(), raw)
            return field.default
    if isinstance(field, List):
        return [x.strip() for x in raw.replace("\n", ",").split(",") if x.strip()]
    return raw.strip()


def env_value(name):
    """Return the raw environment override for ``name`` or None."""
    raw = os.environ.get(ENV_PREFIX + name.upper())
    if raw is None or raw == "":
        return None
    return raw


def _records():
    registry = queryUtility(IRegistry)
    if registry is None:
        return None
    try:
        return registry.forInterface(IOAuth2Settings, prefix=PREFIX, check=False)
    except Exception:  # pragma: no cover - registry not installed yet
        logger.warning("maitux.oauth2 registry records are not available")
        return None


def get(name, default=_marker):
    """Return a single setting, environment first, then registry, then schema."""
    raw = env_value(name)
    if raw is not None:
        return _coerce(name, raw)

    registry = queryUtility(IRegistry)
    if registry is not None:
        key = PREFIX + "." + name
        if key in registry.records:
            # The record exists, so its value is authoritative -- including an
            # empty one.  Falling back to the schema default here would make a
            # deliberately cleared field impossible to clear (and would revive
            # whatever value happened to be hard coded in the schema).
            value = registry.records[key].value
            if value is None and _is_text_field(name):
                # Records created before missing_value was set to u"" hold a
                # real None; treat it as empty rather than letting it leak out.
                return u""
            return value

    if default is not _marker:
        return default
    field = FIELDS.get(name)
    return getattr(field, "default", None)


def set_value(name, value):
    """Persist a setting in the registry (used for last_sync bookkeeping)."""
    records = _records()
    if records is None:
        return False
    # plone.registry is strict about text fields: bytes would raise WrongType
    # on Python 2, where json.dumps() happily hands back a str.
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    try:
        setattr(records, name, value)
    except Exception as exc:
        # A record can be absent when the schema gained a field after the
        # profile was installed.  Bookkeeping must never break the caller.
        logger.warning("Could not store setting %s: %s", name, exc)
        return False
    return True


TEXT_FIELD_TYPES = (TextLine, Text)

#: Values that are never a legitimate setting and only ever appear because of
#: a None -> missing_value mismatch somewhere upstream.
BOGUS_TEXT_VALUES = (None, u"None", u"none")


def _is_text_field(name):
    return isinstance(FIELDS.get(name), TEXT_FIELD_TYPES)


def normalize_text_records():
    """Replace bogus text values with an empty string.

    Records created while these fields still had ``missing_value = None`` hold
    a real ``None``.  Once ``missing_value`` became ``u""``, z3c.form stopped
    recognising ``None`` as "empty" and rendered it through ``toUnicode()``,
    i.e. as the literal string ``"None"`` -- which the next save then wrote
    back as a real value.  A ``redirect_uri`` of ``"None"`` gets sent to the
    IdP verbatim and breaks every login, so clean both forms up.

    Returns the list of field names that were fixed.
    """
    registry = queryUtility(IRegistry)
    if registry is None:
        return []
    fixed = []
    for name in FIELDS:
        if not _is_text_field(name):
            continue
        key = PREFIX + "." + name
        if key not in registry.records:
            continue
        value = registry.records[key].value
        if value in BOGUS_TEXT_VALUES:
            registry.records[key].value = u""
            fixed.append(name)
    if fixed:
        logger.warning("Normalised %s bogus text setting(s) to empty: %s",
                       len(fixed), sorted(fixed))
    return fixed


def ensure_records():
    """Create registry records for schema fields added after installation.

    ``plone.app.registry``'s control panel calls ``forInterface()`` *without*
    ``check=False``, so a single missing record makes the whole settings page
    raise ``KeyError``.  ``registerInterface()`` fills the gaps and -- per
    plone.registry's own implementation -- explicitly retains the values of the
    records that already exist, so this is safe on a configured site.

    Returns the list of field names that were missing.
    """
    registry = queryUtility(IRegistry)
    if registry is None:
        return []
    missing = [name for name in FIELDS
               if (PREFIX + "." + name) not in registry.records]
    if missing:
        logger.info("Creating %s missing registry record(s): %s",
                    len(missing), sorted(missing))
        registry.registerInterface(IOAuth2Settings, prefix=PREFIX)
    return missing


def get_all():
    """Return every setting as a plain dict (secrets included -- do not log)."""
    return dict([(name, get(name)) for name in FIELDS])


def is_enabled():
    return bool(get("enabled"))


def base_url():
    """Normalised IDaaS base URL, e.g. ``https://passport.example.com``."""
    url = (get("provider_url") or u"").strip()
    if not url:
        return u""
    if "://" not in url:
        url = u"https://" + url
    return url.rstrip("/")


def endpoint(name):
    """Absolute URL of one of the configured IDaaS endpoints."""
    path = (get(name) or u"").strip()
    if not path:
        return u""
    if "://" in path:
        return path
    if not path.startswith("/"):
        path = u"/" + path
    return base_url() + path


def is_secure_request(request):
    """True when the browser is talking HTTPS, even behind a TLS terminator.

    Zope does not honour ``X-Forwarded-Proto`` unless waitress is configured
    with ``trusted_proxy``, so ``portal_url`` comes out as ``http://`` on a
    site that is actually served over HTTPS through nginx.
    """
    if request is None:
        return False
    url = request.get("ACTUAL_URL") or request.get("URL") or ""
    if url.lower().startswith("https"):
        return True
    try:
        forwarded = request.get_header("X-Forwarded-Proto", "") or ""
    except Exception:
        forwarded = request.get("HTTP_X_FORWARDED_PROTO", "") or ""
    return forwarded.split(",")[0].strip().lower() == "https"


def callback_url(portal_url, request=None):
    """The ``redirect_uri`` for this site.

    Derived per site from ``portal_url`` so that one instance can host several
    SENAITE sites, each with its own callback.  The registry value is only an
    escape hatch for deployments where the derived URL is not reachable from
    outside (it is a *per site* setting -- do not set it through the
    container wide ``MAITUX_OAUTH2_REDIRECT_URI`` environment variable when
    more than one site is installed).
    """
    configured = (get("redirect_uri") or u"").strip()
    if configured:
        return configured
    url = portal_url or u""
    if is_secure_request(request) and url.lower().startswith("http://"):
        url = u"https://" + url[len("http://"):]
    return u"%s/@@oauth2-callback" % url.rstrip("/")


def claims(name):
    """Split a comma separated claim-name setting into a list."""
    raw = get(name) or u""
    return [x.strip() for x in raw.replace("\n", ",").split(",") if x.strip()]


def first_claim(data, setting_name):
    """Return the first non-empty value in ``data`` for the configured claims."""
    return first_claim_and_key(data, setting_name)[0]


def first_claim_and_key(data, setting_name):
    """Like :func:`first_claim` but also reports which key supplied the value.

    Used to log which identity claim 竹云 actually returned, so that a
    deployment can see at a glance whether ``external_id`` came through or the
    fallback was used.
    """
    for key in claims(setting_name):
        value = data.get(key)
        if value is None or isinstance(value, bool):
            continue
        if isinstance(value, bytes):
            value = value.decode("utf-8", "replace")
        if not isinstance(value, (str, type(u""))):
            value = u"%s" % value
        value = value.strip()
        if value:
            return value, key
    return u"", None
