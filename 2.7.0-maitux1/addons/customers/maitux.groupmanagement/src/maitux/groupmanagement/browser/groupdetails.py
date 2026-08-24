# -*- coding: utf-8 -*-
"""独立组管理：组属性 / 新建组视图

直接复用 CMFPlone 的 GroupDetailsControlPanel 全部逻辑
（新建组、编辑组属性），仅通过 add-on 自己的模板替换导航链接。
"""

from Products.CMFPlone.controlpanel.browser.usergroups_groupdetails import \
    GroupDetailsControlPanel as BaseView


class GroupDetailsView(BaseView):
    """组属性/新建组（独立组管理界面的子页）"""
    pass
