# -*- coding: utf-8 -*-
"""@@lims-setup 扩展：追加"组管理"入口 tile

senaite.core 的 SetupView 只渲染 setup 文件夹内的内容对象。
本模块在其基础上追加一个虚拟条目，指向独立的组管理视图
``@@maitux-group-management``，并为其提供 FontAwesome 图标。
"""

from bika.lims import api
from senaite.core.browser.controlpanel.setupview import SetupView as BaseSetupView

from maitux.groupmanagement.config import INSTALLED_PROPERTY

GROUP_MANAGEMENT_TITLE = "Group Management"
GROUP_MANAGEMENT_VIEW = "@@maitux-group-management"
GROUP_MANAGEMENT_ICON = "fas fa-users-cog"


class SetupEntry(object):
    """@@lims-setup 页面上组管理入口的虚拟 tile 对象

    只提供 setupview.pt 模板所需的最小子集：
      - ``Title`` / ``absolute_url``（tile 标题与链接）
      - ``objectIds()``（get_count 的兜底路径，返回空列表）
    """

    def __init__(self, title, url):
        self.Title = title
        self.absolute_url = url

    def objectIds(self):
        return []


class SetupView(BaseSetupView):
    """在 SENAITE Setup 页面追加"组管理"入口"""

    def setupitems(self):
        """追加组管理虚拟条目到现有 setup items

        仅当 add-on 已安装（portal 上有安装标记）时追加，
        保证卸载后即使浏览器层残留，@@lims-setup 上也不显示入口。
        """
        items = super(SetupView, self).setupitems()
        if self._is_installed():
            items.append(self._get_group_management_entry())
        return items

    def _is_installed(self):
        """检查本 add-on 的安装标记"""
        portal = api.get_portal()
        try:
            return portal.getProperty(INSTALLED_PROPERTY, False) is True
        except Exception:  # noqa: B902
            return False

    def _get_group_management_entry(self):
        """构造组管理入口的虚拟 tile"""
        portal = api.get_portal()
        url = "{}/{}".format(portal.absolute_url(), GROUP_MANAGEMENT_VIEW)
        return SetupEntry(GROUP_MANAGEMENT_TITLE, url)

    def get_count(self, obj):
        """虚拟条目没有子项，始终返回 0（不显示计数徽标）"""
        if isinstance(obj, SetupEntry):
            return 0
        return super(SetupView, self).get_count(obj)

    def get_icon_for(self, brain, **kw):
        """虚拟条目使用 FontAwesome 图标，其余走默认内容类型图标"""
        if isinstance(brain, SetupEntry):
            css = kw.get("css_class", "")
            cls = GROUP_MANAGEMENT_ICON
            if css:
                cls = "{} {}".format(cls, css)
            return '<i class="{}" title="{}"></i>'.format(
                cls, GROUP_MANAGEMENT_TITLE)
        return super(SetupView, self).get_icon_for(brain, **kw)
