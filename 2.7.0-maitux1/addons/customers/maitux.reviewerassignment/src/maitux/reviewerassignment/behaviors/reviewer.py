# -*- coding: utf-8 -*-
"""工作表审核人行为"""

from AccessControl import ClassSecurityInfo
from plone.autoform.interfaces import IFormFieldProvider
from plone.behavior.interfaces import IBehavior
from plone.supermodel import model
from senaite.core.behaviors.utils import get_behavior_schema
from zope import schema
from zope.interface import implementer
from zope.interface import provider


@provider(IFormFieldProvider)
class IWorksheetReviewerBehavior(model.Schema):
    """工作表审核人字段定义"""

    reviewer_userid = schema.TextLine(
        title=u"审核人",
        description=u"保存被分配审核人的用户 ID，供过滤和权限校验使用",
        required=False,
        default=u"",
    )


@implementer(IBehavior, IWorksheetReviewerBehavior)
class WorksheetReviewerBehaviorFactory(object):
    """行为工厂，给工作表提供审核人字段"""

    security = ClassSecurityInfo()

    def __init__(self, context):
        self.context = context
        self._schema = None

    @property
    def schema(self):
        """延迟获取扩展后的 schema"""
        if self._schema is None:
            self._schema = get_behavior_schema(
                self.context, IWorksheetReviewerBehavior)
        return self._schema

    def getReviewerUserid(self):
        """读取审核人用户 id"""
        return self.schema["reviewer_userid"].get(self.context) or u""

    def setReviewerUserid(self, value):
        """写入审核人用户 id"""
        self.schema["reviewer_userid"].set(self.context, value or u"")

    reviewer_userid = property(getReviewerUserid, setReviewerUserid)
