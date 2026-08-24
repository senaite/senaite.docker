# -*- coding: utf-8 -*-
"""maitux.groupmanagement 接口定义

浏览器层（Browser Layer）是 add-on 覆盖 senaite.core 同名视图的标准机制：
当本 layer 出现在请求上时（profile 安装后生效），注册在
IMaituxGroupManagementLayer 上的视图比注册在 ISenaiteCore 上的同名视图
更具体，因此 ZCML 会优先选中本 add-on 的视图。
"""

from plone.theme.interfaces import IDefaultPloneLayer
from senaite.core.interfaces import ISenaiteCore
from zope.interface import Interface


class IMaituxGroupManagementLayer(ISenaiteCore, IDefaultPloneLayer):
    """maitux.groupmanagement 浏览器层

    继承 senaite.core 的 ISenaiteCore，确保在本 add-on 安装后：
      - ``@@lims-setup`` 被本 add-on 的 SetupView 子类覆盖
      - 独立组管理视图（``@@maitux-group-management`` 等）可用
    """


class IGroupManagementEntry(Interface):
    """@@lims-setup 上组管理虚拟入口的 Marker

    仅用于标识 setupitems() 返回的虚拟条目，便于视图内部判断。
    """
