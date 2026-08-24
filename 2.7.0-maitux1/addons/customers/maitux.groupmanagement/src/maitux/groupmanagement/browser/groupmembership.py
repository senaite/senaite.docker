# -*- coding: utf-8 -*-
"""独立组管理：组成员视图

直接复用 CMFPlone 的 GroupMembershipControlPanel 全部逻辑
（成员搜索、添加成员、移出成员），仅通过 add-on 自己的模板
替换导航链接。按需求确认，"移出成员"（非删除组）予以保留。
"""

from Products.CMFPlone.controlpanel.browser.usergroups_groupmembership import \
    GroupMembershipControlPanel as BaseView


class GroupMembershipView(BaseView):
    """组成员管理（独立组管理界面的子页）"""
    pass
