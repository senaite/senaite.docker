# -*- coding: utf-8 -*-
"""模块根容器 —— SENAITE 侧边栏中的顶层导航节点"""

from plone.supermodel import model
from senaite.core.content.base import Container
from senaite.core.interfaces import IHideActionsMenu
from zope.interface import implementer

from maitux.reviewerassignment.interfaces import IReviewerAssignmentContainer


class IReviewerAssignmentContainerSchema(model.Schema):
    """根容器 schema，当前仅作为菜单入口使用"""
    pass


@implementer(IReviewerAssignmentContainer)
@implementer(IHideActionsMenu)
class ReviewerAssignmentContainer(Container):
    """审核工作表根容器"""
    pass
