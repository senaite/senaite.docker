# -*- coding: utf-8 -*-
"""模块根容器 —— SENAITE 侧边栏中的顶层导航节点"""

from plone.supermodel import model
from senaite.core.content.base import Container
from senaite.core.interfaces import IHideActionsMenu
from zope.interface import implementer


class IWorkflowContainerSchema(model.Schema):
    """Schema 定义（空表示纯容器，无需额外字段）"""
    pass


@implementer(IHideActionsMenu)
class WorkflowContainer(Container):
    """
    根容器类。

    继承 senaite.core.content.base.Container 获得：
      - 完整的文件夹行为
      - 标准的权限模型
      - 与 SENAITE 侧边栏的集成

    实现 IHideActionsMenu 隐藏不必要的操作菜单。
    """
    pass
