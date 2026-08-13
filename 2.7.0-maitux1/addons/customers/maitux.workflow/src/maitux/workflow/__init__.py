# -*- coding: utf-8 -*-
from zope.i18nmessageid import MessageFactory

workflowMessageFactory = MessageFactory('maitux.workflow')

def initialize(context):
    """工具：Zope 2 产品初始化钩子"""
    from maitux.workflow import content
    content.initialize(context)
