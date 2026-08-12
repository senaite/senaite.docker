# -*- coding: utf-8 -*-
"""Re-authentication providers for the electronic signature MVP."""

from AccessControl import getSecurityManager
from bika.lims.api.user import get_user_id
from plone import api
from Products.PluggableAuthService.interfaces.plugins import IAuthenticationPlugin


class ReAuthResult(dict):
    """Small mapping wrapper for re-auth results."""

    @classmethod
    def success(cls, backend_id, user_id):
        return cls({
            "authenticated": True,
            "backend_id": backend_id,
            "user_id": user_id,
            "failure_reason": None,
        })

    @classmethod
    def failure(cls, backend_id, user_id, reason):
        return cls({
            "authenticated": False,
            "backend_id": backend_id,
            "user_id": user_id,
            "failure_reason": reason,
        })


class BaseReAuthenticationProvider(object):
    """Base provider contract for current-user re-authentication."""

    backend_id = "unknown"

    def supports_interactive_reauth(self):
        return True

    def authenticate_current_user(self, user_id, credential, request_context=None):
        raise NotImplementedError()

    def authenticate_user(self, user_id, credential, request_context=None):
        """校验任意指定用户，供双人复核时验证第二复核人使用。"""
        raise NotImplementedError()


class PasReAuthenticationProvider(BaseReAuthenticationProvider):
    """MVP provider that reuses the portal PAS authentication chain."""

    backend_id = "pas"

    def __init__(self, portal=None):
        self.portal = portal or api.portal.get()

    def _candidate_acl_users(self):
        """返回可能的用户目录，优先使用当前登录用户实际所在的 user folder。"""
        current_user = getSecurityManager().getUser()
        seen = set()

        # 优先使用当前已登录用户实际挂靠的 user folder，保证与真实登录链一致。
        current_user_folder = getattr(current_user, "aq_parent", None)
        if current_user_folder is not None:
            path = tuple(getattr(current_user_folder, "getPhysicalPath", lambda: ())())
            if path not in seen:
                seen.add(path)
                yield current_user_folder

        # 再尝试站点级 acl_users，兼容标准站点内 PAS。
        portal_acl = getattr(self.portal, "acl_users", None)
        if portal_acl is not None:
            path = tuple(getattr(portal_acl, "getPhysicalPath", lambda: ())())
            if path not in seen:
                seen.add(path)
                yield portal_acl

        # 最后回退到根级 acl_users，兼容管理员账号挂在 Zope 根上的场景。
        root = getattr(self.portal, "getPhysicalRoot", lambda: None)()
        root_acl = getattr(root, "acl_users", None) if root is not None else None
        if root_acl is not None:
            path = tuple(getattr(root_acl, "getPhysicalPath", lambda: ())())
            if path not in seen:
                seen.add(path)
                yield root_acl

    def _authenticate_with_pas(self, acl_users, credentials):
        authenticate = getattr(acl_users, "authenticateCredentials", None)
        if authenticate is not None:
            authenticated = authenticate(credentials)
            if authenticated:
                return authenticated

        plugins = getattr(acl_users, "plugins", None)
        if plugins is None:
            return None

        for _plugin_id, plugin in plugins.listPlugins(IAuthenticationPlugin):
            authenticate = getattr(plugin, "authenticateCredentials", None)
            if authenticate is None:
                continue
            authenticated = authenticate(credentials)
            if authenticated:
                return authenticated

        return None

    def _authenticate_user(self, user_id, credential):
        if not credential:
            return ReAuthResult.failure(
                self.backend_id,
                user_id,
                "missing_credential",
            )

        credentials = {
            "login": user_id,
            "password": credential,
        }
        authenticated = None
        for acl_users in self._candidate_acl_users():
            authenticated = self._authenticate_with_pas(acl_users, credentials)
            if authenticated:
                break
        if not authenticated:
            return ReAuthResult.failure(
                self.backend_id,
                user_id,
                "invalid_credentials",
            )

        authenticated_user_id = authenticated[0]
        if authenticated_user_id != user_id:
            return ReAuthResult.failure(
                self.backend_id,
                user_id,
                "authenticated_user_mismatch",
            )

        return ReAuthResult.success(self.backend_id, user_id)

    def authenticate_current_user(self, user_id, credential, request_context=None):
        current_user_id = get_user_id()
        if not current_user_id or current_user_id != user_id:
            return ReAuthResult.failure(
                self.backend_id,
                user_id,
                "current_session_user_mismatch",
            )
        return self._authenticate_user(user_id, credential)

    def authenticate_user(self, user_id, credential, request_context=None):
        # 这里不要求与当前会话用户一致，供双人复核场景验证第二复核人账号。
        return self._authenticate_user(user_id, credential)
