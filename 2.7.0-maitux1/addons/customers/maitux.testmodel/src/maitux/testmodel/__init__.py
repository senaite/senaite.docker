# -*- coding: utf-8 -*-
from zope.i18nmessageid import MessageFactory

testmodelMessageFactory = MessageFactory('maitux.testmodel')

def initialize(context):
    """工具：Zope 2 产品初始化钩子"""
    from maitux.testmodel import content
    content.initialize(context)
