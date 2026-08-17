# -*- coding: utf-8 -*-
from zope.i18nmessageid import MessageFactory


audittrailMessageFactory = MessageFactory("maitux.audittrail")


def initialize(context):
    """预留 Zope 2 产品初始化钩子。"""
