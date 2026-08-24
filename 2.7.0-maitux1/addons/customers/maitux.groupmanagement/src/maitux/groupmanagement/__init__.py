# -*- coding: utf-8 -*-
from zope.i18nmessageid import MessageFactory

groupmanagementMessageFactory = MessageFactory('maitux.groupmanagement')


def initialize(context):
    """工具：Zope 2 产品初始化钩子

    本 add-on 不包含内容类型，无需额外初始化。
    """
    return
