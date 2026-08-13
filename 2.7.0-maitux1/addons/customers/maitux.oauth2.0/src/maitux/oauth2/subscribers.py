# -*- coding: utf-8 -*-
"""Traversal time hooks.

Two things happen once per request, on the site root traversal:

1. **Disabled accounts are kicked out.**  The daily sync flags leavers, but a
   leaver may still hold a valid ``__ac`` cookie, so the session has to be
   terminated the next time it is used.

2. **Optionally, ``/login`` is sent to 竹云 too.**  This is done here rather
   than by overriding the ``login`` view, because replacing Plone's login
   FormWrapper is the one change that could lock every administrator out.

Both must stay cheap and must never write to the ZODB.
"""

from Products.CMFCore.utils import getToolByName
from six.moves.urllib.parse import urlencode
from zExceptions import Redirect

from maitux.oauth2 import config
from maitux.oauth2 import logger
from maitux.oauth2 import safe_text
from maitux.oauth2 import state as state_util
from maitux.oauth2 import users

GUARD_KEY = "_maitux_oauth2_checked"

#: Paths that must stay reachable for a disabled user, otherwise we would build
#: a redirect loop (or lock an administrator out of the ZMI).
SAFE_PATH_MARKERS = (
    "/@@oauth2-",
    "/logout",
    "/logged_out",
    "/acl_users",
    "/manage",
    "/++resource++",
    "/++plone++",
    "/++theme++",
    "/portal_css",
    "/portal_javascripts",
    "/senaite_theme",
)

#: Views that ``redirect_login_form`` sends to 竹云.
LOGIN_VIEW_NAMES = ("login", "login_form", "@@login", "@@login_form")


def _is_safe(url):
    lowered = (url or "").lower()
    for marker in SAFE_PATH_MARKERS:
        if marker in lowered:
            return True
    return False


def _view_name(url):
    return (url or "").rstrip("/").rsplit("/", 1)[-1].lower()


def enforce_account_state(site, event):
    """``IBeforeTraverseEvent`` handler on the Plone site."""
    request = getattr(event, "request", None)
    if request is None:
        return

    # Only look at the outermost traversal of a request.
    if request.get(GUARD_KEY):
        return
    try:
        request.set(GUARD_KEY, True)
    except Exception:  # pragma: no cover - not a real request object
        return

    try:
        if not config.is_enabled():
            return

        url = request.get("ACTUAL_URL") or request.get("URL") or ""
        membership = getToolByName(site, "portal_membership", None)
        if membership is None:
            return
        anonymous = membership.isAnonymousUser()

        if anonymous:
            _maybe_redirect_login_form(site, request, url)
            return

        if not config.get("enforce_disabled"):
            return
        member = membership.getAuthenticatedMember()
        if not users.is_disabled(member):
            return
        if _is_safe(url):
            return

        logger.info(u"Blocking disabled SSO member %s on %s", member.getId(), url)
        membership.logoutUser(request)
        raise Redirect("%s/@@oauth2-disabled" % site.absolute_url())
    except Redirect:
        raise
    except Exception as exc:  # never break the site because of this check
        logger.warning("enforce_account_state failed: %s", safe_text(exc))


def _maybe_redirect_login_form(site, request, url):
    """Send an anonymous visitor of ``/login`` straight to 竹云 (opt-in)."""
    if not config.get("redirect_login_form") or not config.get("auto_redirect"):
        return
    if (request.get("REQUEST_METHOD") or "GET").upper() != "GET":
        # Never swallow a credentials POST -- that would break the escape hatch.
        return
    if _view_name(url) not in LOGIN_VIEW_NAMES:
        return
    if request.get(state_util.BYPASS_COOKIE):
        return

    target = "%s/@@oauth2-login" % site.absolute_url()
    came_from = request.get("came_from")
    if came_from:
        target = "%s?%s" % (target, urlencode({"came_from": came_from}))
    raise Redirect(target)
