# -*- coding: utf-8 -*-
from zope.i18nmessageid import MessageFactory

reviewerassignmentMessageFactory = MessageFactory('maitux.reviewerassignment')

# Allow importing this package's modules from restricted page-template code
# (e.g. modules['maitux.reviewerassignment.assignment'] in print templates).
from AccessControl.SecurityInfo import ModuleSecurityInfo

ModuleSecurityInfo("maitux").declarePublic("__path__")
ModuleSecurityInfo("maitux.reviewerassignment").declarePublic("__path__")
ModuleSecurityInfo("maitux.reviewerassignment.assignment").declarePublic(
    "get_reviewer_userid", "get_member_fullname", "iter_reviewer_options")

def initialize(context):
    """工具：Zope 2 产品初始化钩子"""
    from maitux.reviewerassignment import content
    content.initialize(context)
