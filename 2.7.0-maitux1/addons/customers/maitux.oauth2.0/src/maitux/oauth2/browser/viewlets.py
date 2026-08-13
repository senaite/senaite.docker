# -*- coding: utf-8 -*-
"""Adds a "竹云统一登录" button to the standard Plone login form.

SENAITE ships its own login template, so rather than trying to override it the
button is injected client side.  If the markup ever changes, the worst that can
happen is that no button shows up -- ``@@oauth2-login`` keeps working.
"""

from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from plone import api
from plone.app.layout.viewlets.common import ViewletBase
from six.moves.urllib.parse import urlencode

from maitux.oauth2 import config

LOGIN_VIEW_NAMES = ("login", "login_form", "require_login", "logged_out",
                    "failsafe_login_form")


class LoginButtonViewlet(ViewletBase):
    index = ViewPageTemplateFile("templates/login_button.pt")

    def available(self):
        if not config.is_enabled() or not config.get("show_login_button"):
            return False
        if not api.user.is_anonymous():
            return False
        url = (self.request.get("ACTUAL_URL") or u"").rstrip("/")
        name = url.rsplit("/", 1)[-1]
        return name in LOGIN_VIEW_NAMES

    def login_url(self):
        portal_url = api.portal.get().absolute_url()
        came_from = self.request.form.get("came_from") or u""
        if came_from:
            return u"%s/@@oauth2-login?%s" % (
                portal_url, urlencode({"came_from": came_from}))
        return u"%s/@@oauth2-login" % portal_url

    def render(self):
        if not self.available():
            return u""
        return self.index()
