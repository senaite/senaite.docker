# -*- coding: utf-8 -*-
"""审核人字段访问辅助函数"""

from bika.lims.utils import getUsers
from Products.CMFCore.utils import getToolByName
from zope.annotation.interfaces import IAnnotations

from maitux.reviewerassignment.behaviors.reviewer import (
    IWorksheetReviewerBehavior,
)

REVIEWER_ANNOTATION_KEY = "maitux.reviewerassignment.reviewer_userid"


def get_reviewer_userid(context):
    """读取对象上的审核人用户 id

    - Worksheet 优先走 behavior 字段
    - 其他对象（如 Analysis）走 annotations 兜底
    """
    try:
        behavior = IWorksheetReviewerBehavior(context)
    except TypeError:
        behavior = None

    if behavior is not None:
        return behavior.reviewer_userid or u""

    try:
        annotations = IAnnotations(context)
    except TypeError:
        return u""
    return annotations.get(REVIEWER_ANNOTATION_KEY, u"") or u""


def set_reviewer_userid(context, reviewer_userid):
    """写入对象上的审核人用户 id"""
    try:
        behavior = IWorksheetReviewerBehavior(context)
    except TypeError:
        behavior = None

    if behavior is not None:
        behavior.reviewer_userid = reviewer_userid or u""
        return

    annotations = IAnnotations(context)
    annotations[REVIEWER_ANNOTATION_KEY] = reviewer_userid or u""


def iter_reviewer_options(context):
    """返回审核人下拉框选项"""
    reviewers = getUsers(context, ["Verifier"], allow_empty=False)
    for userid in reviewers.sortedByValue():
        yield userid, reviewers.getValue(userid)


def get_member_fullname(context, userid):
    """按用户 id 获取全名，找不到时回退到 id"""
    if not userid:
        return u""
    membership = getToolByName(context, "portal_membership")
    member = membership.getMemberById(userid)
    if member is None:
        return userid
    fullname = member.getProperty("fullname")
    return fullname or userid
