# -*- coding: utf-8 -*-
"""Client for the Bamboocloud (竹云) IDaaS OAuth 2.0 and EIAM APIs.

Endpoints implemented (see https://open.bccastle.com/development/):

* ``GET  /api/v1/oauth2/authorize``  获取标准授权码
* ``POST /api/v1/oauth2/token``      获取 Access Token
* ``GET  /api/v1/oauth2/userinfo``   获取用户信息
* ``POST /api/v1/oauth2/introspect`` 检查 Token 有效性
* ``GET  /api/v1/logout``            全局退出
* ``POST /api/v2/tenant/token``      EIAM 鉴权 (client_credentials)
* ``GET  /api/v2/tenant/users``      EIAM 获取用户列表
"""

from six.moves.urllib.parse import urlencode

from maitux.oauth2 import config
from maitux.oauth2 import logger
from maitux.oauth2.httputils import HttpError
from maitux.oauth2.httputils import basic_auth_header
from maitux.oauth2.httputils import request_json


class OAuth2Error(Exception):
    """竹云 answered with an OAuth2 error payload."""

    def __init__(self, error, description=None, status=None):
        message = error or u"unknown_error"
        if description:
            message = u"%s: %s" % (message, description)
        super(OAuth2Error, self).__init__(message)
        self.error = error
        self.description = description
        self.status = status


def _error_from(data, status):
    error = data.get("error") or data.get("error_code")
    if not error:
        return None
    description = data.get("error_description") or data.get("error_msg")
    return OAuth2Error(error, description, status)


class BCastleClient(object):
    """Thin, stateless wrapper around the 竹云 HTTP API."""

    def __init__(self):
        self.client_id = config.get("client_id") or u""
        self.client_secret = config.get("client_secret") or u""
        self.timeout = config.get("request_timeout") or 15
        self.verify_ssl = bool(config.get("verify_ssl"))

    # -- helpers ------------------------------------------------------

    @property
    def _basic_auth(self):
        return basic_auth_header(self.client_id, self.client_secret)

    def _call(self, url, method="GET", form=None, headers=None):
        if not url:
            raise HttpError(u"竹云接口地址未配置")
        status, data = request_json(
            url,
            method=method,
            form=form,
            headers=headers,
            timeout=self.timeout,
            verify_ssl=self.verify_ssl,
        )
        error = _error_from(data, status)
        if error is not None:
            raise error
        if status < 200 or status >= 300:
            raise HttpError(
                u"竹云接口返回 HTTP %s" % status, status=status, body=data)
        return data

    # -- OAuth2 login -------------------------------------------------

    def authorize_url(self, state, redirect_uri):
        """Build the 竹云 authorisation URL the browser is sent to."""
        params = [
            ("response_type", "code"),
            ("client_id", self.client_id),
        ]
        if redirect_uri:
            params.append(("redirect_uri", redirect_uri))
        scope = config.get("scope")
        if scope:
            params.append(("scope", scope))
        if state:
            params.append(("state", state))
        return u"%s?%s" % (config.endpoint("authorize_path"), urlencode(params))

    def exchange_code(self, code, redirect_uri):
        """授权码换 access_token."""
        form = {"grant_type": "authorization_code", "code": code}
        if redirect_uri:
            form["redirect_uri"] = redirect_uri
        return self._call(
            config.endpoint("token_path"),
            method="POST",
            form=form,
            headers={"Authorization": self._basic_auth},
        )

    def get_userinfo(self, access_token):
        """携带 access_token 获取用户身份."""
        return self._call(
            config.endpoint("userinfo_path"),
            headers={"Authorization": u"Bearer %s" % access_token},
        )

    def introspect(self, token):
        """检查 token 是否仍然有效."""
        return self._call(
            config.endpoint("introspect_path"),
            method="POST",
            form={"token": token, "token_type_hint": "access_token"},
            headers={"Authorization": self._basic_auth},
        )

    def logout_url(self, redirect_url):
        """竹云全局退出地址."""
        url = config.endpoint("idp_logout_path")
        if not url:
            return u""
        params = []
        if redirect_url:
            params.append(("redirect_url", redirect_url))
        if self.client_id:
            params.append(("client_id", self.client_id))
        if params:
            url = u"%s?%s" % (url, urlencode(params))
        return url

    # -- EIAM (daily user sync) ---------------------------------------

    def eiam_token(self):
        """client_credentials token for the 身份管理 API."""
        data = self._call(
            config.endpoint("eiam_token_path"),
            method="POST",
            form={"grant_type": "client_credentials"},
            headers={"Authorization": self._basic_auth},
        )
        token = data.get("access_token")
        if not token:
            raise HttpError(u"EIAM 鉴权接口未返回 access_token", body=data)
        return token

    def iter_eiam_users(self, token=None, org_id=None, page_size=None,
                        updated_after=None):
        """Yield every user record from ``/api/v2/tenant/users``.

        The endpoint is paginated (``offset`` is a *page* index starting at 0,
        ``limit`` must be between 10 and 100).
        """
        token = token or self.eiam_token()
        org_id = org_id if org_id is not None else (config.get("sync_org_id") or u"")
        page_size = page_size or config.get("sync_page_size") or 100
        page_size = max(10, min(100, int(page_size)))

        headers = {
            "Authorization": u"Bearer %s" % token,
            "Content-Type": "application/json; charset=utf-8",
        }
        base = config.endpoint("eiam_users_path")

        offset = 0
        seen = 0
        total = None
        while True:
            params = [("offset", offset), ("limit", page_size)]
            if org_id:
                params.append(("org_id", org_id))
            if updated_after:
                params.append(("updated_at_greater", updated_after))
            url = u"%s?%s" % (base, urlencode(params))

            data = self._call(url, headers=headers)
            users = data.get("users") or []
            if total is None:
                total = data.get("total")
            for user in users:
                if isinstance(user, dict):
                    seen += 1
                    yield user

            if len(users) < page_size:
                break
            offset += 1
            if total is not None and seen >= total:
                break
            if offset > 10000:  # pragma: no cover - runaway guard
                logger.error("EIAM user pagination did not terminate, aborting")
                break
