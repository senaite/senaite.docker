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

    records = _records()
    if records is not None:
        value = getattr(records, name, None)
        if value is not None:
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
    setattr(records, name, value)
    return True


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


def claims(name):
    """Split a comma separated claim-name setting into a list."""
    raw = get(name) or u""
    return [x.strip() for x in raw.replace("\n", ",").split(",") if x.strip()]


def first_claim(data, setting_name):
    """Return the first non-empty value in ``data`` for the configured claims."""
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
            return value
    return u""
