# -*- coding: utf-8 -*-
"""Control panel for the 竹云统一登录 settings."""

from plone import api
from plone.app.registry.browser import controlpanel

from maitux.oauth2 import _
from maitux.oauth2 import config
from maitux.oauth2.browser.views import disable_csrf
from maitux.oauth2.interfaces import IOAuth2Settings


class OAuth2SettingsEditForm(controlpanel.RegistryEditForm):
    schema = IOAuth2Settings
    schema_prefix = "maitux.oauth2"
    label = _(u"竹云统一登录 (OAuth 2.0)")

    def updateWidgets(self, *args, **kwargs):
        super(OAuth2SettingsEditForm, self).updateWidgets(*args, **kwargs)
        # z3c.form falls back to `field.default` whenever the stored value
        # equals missing_value (u"" for our text fields), so a field the admin
        # deliberately cleared would come back showing the shipped default --
        # even though the runtime correctly treats it as empty.  Make the form
        # agree with what is actually stored.
        content = self.getContent()
        for name in list(self.widgets):
            if getattr(content, name, None) == u"":
                widget = self.widgets[name]
                if widget.value not in (None, u""):
                    widget.value = u""

    def applyChanges(self, data):
        # The password widget deliberately never renders its stored value, so
        # `client_secret` arrives empty on every single save.  Treat "left
        # blank" as "keep what is stored" -- otherwise saving any unrelated
        # setting silently wipes the secret.
        if not (data.get("client_secret") or u"").strip():
            data.pop("client_secret", None)
        return super(OAuth2SettingsEditForm, self).applyChanges(data)

    def getContent(self):
        # plone.app.registry's getContent() calls forInterface() WITHOUT
        # check=False, so one schema field that has no registry record yet
        # (i.e. a field added after this profile was installed) raises
        # KeyError and 500s the whole settings page.  Self-heal instead of
        # forcing a profile re-import.
        if config.ensure_records() or config.normalize_text_records():
            # A legitimate ZODB write on a GET, on a Manage-portal-only page.
            disable_csrf(self.request)
        return super(OAuth2SettingsEditForm, self).getContent()

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
