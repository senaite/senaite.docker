# -*- coding: utf-8 -*-
from zope.i18nmessageid import MessageFactory

reviewerassignmentMessageFactory = MessageFactory('maitux.reviewerassignment')

def initialize(context):
    """工具：Zope 2 产品初始化钩子"""
    from maitux.reviewerassignment import content
    content.initialize(context)
