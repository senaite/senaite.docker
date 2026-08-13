# -*- coding: utf-8 -*-
"""Control panel for the 竹云统一登录 settings."""

from plone import api
from plone.app.registry.browser import controlpanel

from maitux.oauth2 import _
from maitux.oauth2 import config
from maitux.oauth2.interfaces import IOAuth2Settings


class OAuth2SettingsEditForm(controlpanel.RegistryEditForm):
    schema = IOAuth2Settings
    schema_prefix = "maitux.oauth2"
    label = _(u"竹云统一登录 (OAuth 2.0)")

    @property
    def description(self):
        portal_url = api.portal.get().absolute_url()
        callback = (config.get("redirect_uri") or u"").strip() \
            or u"%s/@@oauth2-callback" % portal_url
        overridden = sorted([name for name in config.FIELDS
                             if config.env_value(name) is not None])
        lines = [
            u"需要在竹云登记的回调地址（redirect_uri）：%s" % callback,
            u"管理员本地登录入口（绕过统一登录）：%s/@@oauth2-local-login" % portal_url,
            u"用户同步手动触发：%s/@@oauth2-sync-users" % portal_url,
        ]
        if overridden:
            lines.append(
                u"以下配置项当前被环境变量覆盖，页面上的值不生效：%s"
                % u"、".join(overridden))
        return u" | ".join(lines)


class OAuth2SettingsView(controlpanel.ControlPanelFormWrapper):
    form = OAuth2SettingsEditForm
