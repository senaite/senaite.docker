# -*- coding: utf-8 -*-
"""模块级接口定义"""

from senaite.core.interfaces import ISenaiteCore
from zope.interface import Interface


class IReviewerAssignmentLayer(ISenaiteCore):
    """审核分配浏览器层"""


class IReviewerAssignmentContainer(Interface):
    """审核分配根容器接口"""
