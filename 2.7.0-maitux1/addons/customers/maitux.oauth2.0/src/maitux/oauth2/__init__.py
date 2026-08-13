# -*- coding: utf-8 -*-
"""Bamboocloud (竹云) IDaaS OAuth 2.0 single sign-on for SENAITE."""

import logging

from zope.i18nmessageid import MessageFactory

PROJECTNAME = "maitux.oauth2"

_ = MessageFactory(PROJECTNAME)

logger = logging.getLogger(PROJECTNAME)

TEXT_TYPE = type(u"")


def safe_text(value):
    """Best-effort unicode conversion that cannot blow up on Python 2.

    ``u"...%s" % exc`` raises ``UnicodeDecodeError`` as soon as the exception
    carries a UTF-8 *byte* string, and ``str(exc)`` raises
    ``UnicodeEncodeError`` as soon as it carries a non-ASCII *unicode* string.
    Every error path in this add-on can hit both, so all of them go through
    here -- an exploding error handler hides the actual problem.
    """
    if isinstance(value, TEXT_TYPE):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    try:
        return TEXT_TYPE(value)
    except Exception:
        pass
    try:
        raw = str(value)
    except Exception:
        return u"<unprintable %s>" % type(value).__name__
    if isinstance(raw, bytes):
        return raw.decode("utf-8", "replace")
    return raw
