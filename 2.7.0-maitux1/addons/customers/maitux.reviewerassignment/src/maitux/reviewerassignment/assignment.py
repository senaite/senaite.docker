# -*- coding: utf-8 -*-
"""审核人字段访问辅助函数"""

from bika.lims.utils import getUsers
from Products.CMFCore.utils import getToolByName
from zope.annotation.interfaces import IAnnotations

from maitux.reviewerassignment.behaviors.reviewer import (
    IWorksheetReviewerBehavior,
)
from maitux.reviewerassignment.review_logic import filter_reviewer_candidates
from maitux.reviewerassignment.review_logic import should_exclude_submitter

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
    """返回审核人下拉框选项

    会剔除「未来的提交人」—— 即工作表的被指派分析员。理由见
    get_excluded_reviewer_userid()。
    """
    reviewers = getUsers(context, ["Verifier"], allow_empty=False)
    candidates = [(userid, reviewers.getValue(userid))
                  for userid in reviewers.sortedByValue()]
    excluded = get_excluded_reviewer_userid(context)
    for item in filter_reviewer_candidates(candidates, excluded):
        yield item


def get_excluded_reviewer_userid(context):
    """返回必须从审核人候选中剔除的用户 id，没有则返回空串

    剔除的是**工作表的被指派分析员**，不是当前操作者 —— 因为
    SENAITE 的 guard_submit 在 AllowToSubmitNotAssigned=False 时强制
    「提交人必须是被指派的分析员」，所以未来的提交人是可预知的，
    与谁在界面上操作无关（A 录入选人、B 提交的场景由此被正确处理）。

    是否需要剔除取决于 SENAITE 的自审设置：只要工作表里存在任一分析项不允许自审，
    就把提交人排除掉。这里读的是 SENAITE 的设置，不是本 addon 自己定的规则 ——
    站点把自审打开，过滤自动失效。
    """
    analyst = u""
    getter = getattr(context, "getAnalyst", None)
    if callable(getter):
        try:
            analyst = getter() or u""
        except Exception:
            analyst = u""
    if not analyst:
        return u""

    flags = []
    analyses_getter = getattr(context, "getAnalyses", None)
    if callable(analyses_getter):
        try:
            analyses = analyses_getter() or []
        except Exception:
            analyses = []
        for analysis in analyses:
            checker = getattr(analysis, "isSelfVerificationEnabled", None)
            if not callable(checker):
                continue
            try:
                flags.append(bool(checker()))
            except Exception:
                continue

    if not should_exclude_submitter(flags):
        return u""
    return analyst


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
