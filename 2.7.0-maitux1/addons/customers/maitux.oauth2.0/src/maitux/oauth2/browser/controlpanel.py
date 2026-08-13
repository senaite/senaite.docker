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
        # Exactly the value the login flow will send, so it can be copied
        # verbatim into the 竹云 application's trusted callback list.
        callback = config.callback_url(portal_url, self.request)
        lines = [
            u"① 把这个回调地址交给竹云登记（照抄，不要改）：%s" % callback,
            u"② 管理员本地登录入口（绕过统一登录，万一被锁在外面用）："
            u"%s/@@oauth2-local-login" % portal_url,
            u"③ 手动触发用户同步：%s/@@oauth2-sync-users" % portal_url,
        ]
        overridden = sorted([name for name in config.FIELDS
                             if config.env_value(name) is not None])
        if overridden:
            lines.append(
                u"⚠ 以下配置项被容器环境变量覆盖，本页面上改了也不生效："
                u"%s（环境变量是整个容器共享的，多站点部署请不要用它设置"
                u"站点相关的项）" % u"、".join(overridden))
        return u" | ".join(lines)


class OAuth2SettingsView(controlpanel.ControlPanelFormWrapper):
    form = OAuth2SettingsEditForm
