# -*- coding: utf-8 -*-
"""Browser views implementing the 竹云 OAuth 2.0 login flow.

Two entry points, as required:

1. 用户从竹云 Portal 点击 LIMS 图标 -> 竹云直接带 code 回调 ``@@oauth2-callback``.
2. 用户直接访问 LIMS -> ``require_login`` 把匿名用户送到竹云授权页, 竹云再带
   ``code`` + ``state`` 回调 ``@@oauth2-callback``.

Both land in :class:`CallbackView`, which does the token exchange, the user
lookup and the account-state routing.
"""

import json
from datetime import datetime

from AccessControl import getSecurityManager
from Products.CMFCore.utils import getToolByName
from Products.Five.browser import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from plone import api
from six.moves.urllib.parse import urlencode
from zope.interface import alsoProvides

from maitux.oauth2 import config
from maitux.oauth2 import logger
from maitux.oauth2 import TEXT_TYPE
from maitux.oauth2 import safe_text
from maitux.oauth2 import state as state_util
from maitux.oauth2 import users
from maitux.oauth2.client import BCastleClient
from maitux.oauth2.client import OAuth2Error
from maitux.oauth2.httputils import HttpError
from maitux.oauth2.users import AccountError

try:
    from plone.protect.interfaces import IDisableCSRFProtection
except ImportError:  # pragma: no cover - plone.protect ships with Plone 5
    IDisableCSRFProtection = None


def disable_csrf(request):
    """The SSO callback legitimately writes to the ZODB on a GET request."""
    if IDisableCSRFProtection is not None:
        alsoProvides(request, IDisableCSRFProtection)


def now_string():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class BaseView(BrowserView):

    @property
    def portal(self):
        return api.portal.get()

    @property
    def portal_url(self):
        return self.portal.absolute_url()

    def is_secure(self):
        return config.is_secure_request(self.request)

    def redirect_uri(self):
        # Derived per site; see config.callback_url().
        return config.callback_url(self.portal_url, self.request)

    def safe_came_from(self, candidate):
        """Never let ``came_from`` turn into an open redirect."""
        if not candidate:
            return u""
        try:
            if getToolByName(self.portal, "portal_url").isURLInPortal(candidate):
                return candidate
        except Exception:
            if candidate.startswith(self.portal_url):
                return candidate
        logger.warning("Refusing off-site came_from %r", candidate)
        return u""

    def goto(self, url):
        self.request.response.redirect(url)
        return u""

    def with_came_from(self, url, came_from):
        if not came_from:
            return url
        return u"%s?%s" % (url, urlencode({"came_from": came_from}))

    def message_page(self, title, message, level="info", show_retry=False):
        view = self.portal.restrictedTraverse("@@oauth2-message")
        view.update(title, message, level=level, show_retry=show_retry)
        return view()


# ---------------------------------------------------------------------------
# Step 1 -- send the browser to 竹云
# ---------------------------------------------------------------------------


class LoginView(BaseView):
    """``@@oauth2-login`` -- start the authorisation-code flow."""

    def __call__(self):
        if not config.is_enabled():
            return self.goto(u"%s/login" % self.portal_url)

        came_from = self.safe_came_from(self.request.form.get("came_from"))
        state_util.ensure_secret()
        nonce, cookie = state_util.make_state(came_from)
        state_util.set_cookie(
            self.request.response, state_util.STATE_COOKIE, cookie,
            secure=self.is_secure())
        # Someone who deliberately starts an SSO login is no longer bypassing.
        state_util.clear_cookie(self.request.response, state_util.BYPASS_COOKIE)

        url = BCastleClient().authorize_url(nonce, self.redirect_uri())
        logger.info("Redirecting anonymous visitor to the IdP authorize endpoint")
        return self.goto(url)


class RequireLoginView(BaseView):
    """Overrides Plone's ``require_login``.

    ``credentials_cookie_auth`` challenges to this view, so it is the single
    place where "an anonymous visitor hit something protected" is handled.
    """

    def __call__(self):
        if not api.user.is_anonymous():
            return self.goto(u"%s/insufficient-privileges" % self.portal_url)

        came_from = self.request.form.get("came_from") or u""

        if self.use_sso():
            return self.goto(self.with_came_from(
                u"%s/@@oauth2-login" % self.portal_url, came_from))

        return self.goto(self.with_came_from(
            u"%s/login" % self.portal_url, came_from))

    def use_sso(self):
        if not config.is_enabled() or not config.get("auto_redirect"):
            return False
        # Administrator escape hatch, see LocalLoginView.
        if self.request.get(state_util.BYPASS_COOKIE):
            return False
        return True


class LocalLoginView(BaseView):
    """``@@oauth2-local-login`` -- administrator escape hatch.

    Sets a cookie that switches the SSO auto-redirect off for this browser and
    then shows the ordinary Plone login form.
    """

    def __call__(self):
        state_util.set_cookie(
            self.request.response, state_util.BYPASS_COOKIE, "1",
            max_age=3600, secure=self.is_secure())
        return self.goto(u"%s/login" % self.portal_url)


# ---------------------------------------------------------------------------
# Step 2 -- 竹云 comes back with the authorisation code
# ---------------------------------------------------------------------------


class CallbackView(BaseView):
    """``@@oauth2-callback`` -- exchange the code and log the user in."""

    def __call__(self):
        disable_csrf(self.request)
        request = self.request

        if not config.is_enabled():
            return self.goto(u"%s/login" % self.portal_url)

        error = request.form.get("error")
        if error:
            description = request.form.get("error_description") or u""
            logger.warning("IdP returned an error: %s %s", error, description)
            return self.message_page(
                u"统一登录失败",
                u"竹云返回错误：%s %s" % (error, description),
                level="error", show_retry=True)

        code = request.form.get("code")
        if not code:
            return self.message_page(
                u"统一登录失败", u"回调缺少授权码 code。",
                level="error", show_retry=True)

        came_from = self.validate_state()
        if came_from is None:
            return self.message_page(
                u"统一登录失败",
                [u"安全校验未通过（state 不匹配）。",
                 u"最常见的原因是**登录停留太久**（超过 30 分钟），"
                 u"次常见原因是直接手工访问了回调地址、"
                 u"或浏览器阻止了 Cookie。",
                 u"点下方“重新登录”重试即可。"],
                level="error", show_retry=True)

        state_util.clear_cookie(request.response, state_util.STATE_COOKIE)

        client = BCastleClient()
        try:
            tokens = client.exchange_code(code, self.redirect_uri())
            access_token = tokens.get("access_token")
            if not access_token:
                raise HttpError(u"竹云未返回 access_token")
            userinfo = client.get_userinfo(access_token)
        except OAuth2Error as exc:
            logger.warning("Token/userinfo exchange failed: %s", safe_text(exc))
            return self.message_page(
                u"统一登录失败", u"竹云接口返回错误：%s" % safe_text(exc),
                level="error", show_retry=True)
        except HttpError as exc:
            logger.error("Token/userinfo exchange failed: %s", safe_text(exc))
            return self.message_page(
                u"统一登录失败", safe_text(exc), level="error", show_retry=True)

        subject, subject_key = config.first_claim_and_key(
            userinfo, "userid_claim")
        # Field NAMES only -- the values contain PII (mobile, email, real name).
        logger.info("IdP userinfo returned fields %s; unique id taken from %r",
                    sorted(userinfo.keys()), subject_key)
        if not subject:
            logger.error("No unique id in userinfo, available keys: %s",
                         sorted(userinfo.keys()))
            return self.message_page(
                u"统一登录失败",
                u"竹云返回的用户信息中没有唯一标识（配置的字段：%s）。"
                u"请在竹云应用的属性映射里把外部 ID 返回给本应用，"
                u"或修改本插件的“唯一 ID 字段”配置。"
                % (config.get("userid_claim") or u""),
                level="error")

        username = config.first_claim(userinfo, "username_claim") or subject
        fullname = config.first_claim(userinfo, "fullname_claim")
        email = config.first_claim(userinfo, "email_claim")

        portal = self.portal
        try:
            userid = users.resolve_user(portal, subject, username, fullname, email)
        except AccountError as exc:
            logger.warning("Account resolution failed for %s: %s", subject, safe_text(exc))
            return self.message_page(u"无法登录", safe_text(exc), level="error")

        member = users.get_member(portal, userid)

        if users.is_disabled(member):
            logger.info(u"Rejected disabled member %s", userid)
            return self.goto(u"%s/@@oauth2-disabled" % self.portal_url)

        if users.is_pending(portal, member) \
                and not config.get("login_pending_users"):
            logger.info(u"Member %s is still awaiting authorisation", userid)
            return self.goto(u"%s/@@oauth2-pending" % self.portal_url)

        if not self.start_session(userid):
            return self.message_page(
                u"统一登录失败",
                u"无法建立本地会话，请联系管理员检查 acl_users 的 session 插件。",
                level="error")

        users.set_member_properties(
            portal, userid, {users.PROP_LAST_LOGIN: now_string()})
        logger.info(u"SSO login succeeded for %s (subject=%s)", userid, subject)

        return self.goto(self.safe_came_from(came_from) or self.portal_url)

    # -- helpers ------------------------------------------------------

    def validate_state(self):
        """Return ``came_from``, or ``None`` when the state is invalid.

        竹云 Portal initiated logins (场景 1) arrive without a state and without
        our cookie -- that is legitimate, so they are accepted with an empty
        ``came_from``.  A *mismatching* state is always rejected.
        """
        cookie = self.request.get(state_util.STATE_COOKIE)
        param = self.request.form.get("state")
        if not cookie and not param:
            if config.get("require_state"):
                logger.warning(
                    "Rejecting a callback without state (require_state is on)")
                return None
            logger.info("Callback without state -- treating as IdP initiated login")
            return u""
        try:
            return state_util.read_state(cookie, param)
        except ValueError as exc:
            logger.warning("State validation failed: %s", safe_text(exc))
            return None

    def start_session(self, userid):
        """Create the Plone ``__ac`` session cookie for ``userid``."""
        acl_users = getToolByName(self.portal, "acl_users")
        plugin = getattr(acl_users, "session", None)
        if plugin is None or not hasattr(plugin, "_setupSession"):
            plugin = None
            for candidate in acl_users.objectValues():
                if hasattr(candidate, "_setupSession"):
                    plugin = candidate
                    break
        if plugin is None:
            logger.error("No plone.session plugin found in acl_users")
            return False
        try:
            plugin._setupSession(userid, self.request.response)
        except Exception as exc:
            logger.error("Could not create session for %s: %s", userid, safe_text(exc))
            return False
        return True


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


class LogoutView(BaseView):
    """Overrides Plone's ``logout`` so that the 竹云 SSO ticket dies too."""

    def __call__(self):
        disable_csrf(self.request)

        membership = getToolByName(self.portal, "portal_membership", None)
        if membership is not None and not api.user.is_anonymous():
            try:
                membership.logoutUser(self.request)
            except Exception as exc:
                logger.warning("logoutUser failed: %s", safe_text(exc))

        response = self.request.response
        state_util.clear_cookie(response, state_util.STATE_COOKIE)
        state_util.clear_cookie(response, state_util.BYPASS_COOKIE)

        target = u"%s/logged_out" % self.portal_url
        if config.is_enabled() and config.get("sso_logout"):
            idp_url = BCastleClient().logout_url(target)
            if idp_url:
                target = idp_url
        return self.goto(target)


# ---------------------------------------------------------------------------
# Informational pages
# ---------------------------------------------------------------------------


class MessageView(BaseView):
    """``@@oauth2-message`` -- shared template for the terminal pages."""

    template = ViewPageTemplateFile("templates/message.pt")

    title = u""
    paragraphs = ()
    level = "info"
    show_retry = False

    def update(self, title, message, level="info", show_retry=False):
        """``message`` is one paragraph, or a sequence of paragraphs.

        Everything ends up escaped by the template -- never pass markup, and
        never rely on it being rendered as HTML.
        """
        self.title = title
        if isinstance(message, (bytes, TEXT_TYPE)):
            message = [message]
        self.paragraphs = [safe_text(p) for p in message if p]
        self.level = level
        self.show_retry = show_retry

    def css_class(self):
        return {
            "error": "alert alert-danger",
            "warning": "alert alert-warning",
            "info": "alert alert-info",
        }.get(self.level, "alert alert-info")

    def login_url(self):
        return u"%s/@@oauth2-login" % self.portal_url

    def __call__(self):
        return self.template()


class PendingView(MessageView):
    """``@@oauth2-pending`` -- 首次登录，等待管理员分配权限."""

    def __call__(self):
        self.update(
            u"账号已创建，等待管理员分配权限",
            [u"您的账号已通过竹云统一登录成功创建，但尚未获得 LIMS 的使用权限。",
             u"请联系 LIMS 管理员为您分配角色；分配完成后重新登录即可进入系统。"],
            level="warning", show_retry=True)
        return self.template()


class DisabledView(MessageView):
    """``@@oauth2-disabled`` -- 账号已被禁用."""

    def __call__(self):
        self.update(
            u"账号已被禁用",
            [u"您的账号在 LIMS 中已停用（通常是因为竹云中该账号已停用、锁定或已离职）。",
             u"如果您认为这是误操作，请联系 LIMS 管理员。"],
            level="error")
        return self.template()


# ---------------------------------------------------------------------------
# Sync trigger
# ---------------------------------------------------------------------------


class SyncUsersView(BaseView):
    """``@@oauth2-sync-users`` -- run the daily synchronisation.

    Callable either by a logged-in manager, or by an unattended scheduler that
    passes ``?token=<同步触发口令>``.
    """

    def __call__(self):
        disable_csrf(self.request)
        response = self.request.response
        response.setHeader("Content-Type", "application/json; charset=utf-8")

        if not self.authorized():
            response.setStatus(403)
            return self.dump({"error": u"需要管理员权限或正确的 token 参数"})

        from maitux.oauth2 import sync
        dry_run = self.request.form.get("dry_run") in ("1", "true", "yes", "on")
        return self.dump(sync.sync_users(self.portal, dry_run=dry_run))

    #: Refuse to authenticate the unattended trigger with a guessable secret.
    MIN_TOKEN_LENGTH = 16

    def authorized(self):
        if getSecurityManager().checkPermission("Manage portal", self.portal):
            return True
        configured = (config.get("sync_token") or u"").strip()
        if not configured:
            return False
        if len(configured) < self.MIN_TOKEN_LENGTH:
            logger.warning(
                "Refusing token auth for @@oauth2-sync-users: the configured "
                "sync_token is shorter than %s characters",
                self.MIN_TOKEN_LENGTH)
            return False
        return state_util.compare(self.request.form.get("token") or u"", configured)

    def dump(self, data):
        body = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
        if not isinstance(body, bytes):
            body = body.encode("utf-8")
        return body
