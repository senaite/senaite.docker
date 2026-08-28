# -*- coding: utf-8 -*-
"""审核分配的纯逻辑函数

这里故意只放与 Zope/Plone 解耦的逻辑，便于单元测试复用。
"""


VERIFIER_ROLE = "Verifier"
PENDING_REVIEW_STATE = "to_be_verified"


def normalize_userid(value):
    """标准化用户 id，统一把空白值折叠成空字符串"""
    if value is None:
        return ""
    return safe_unicode(value).strip()


def safe_unicode(value):
    """兼容 Python 2/3 的简单文本转换"""
    try:
        text_type = unicode
    except NameError:  # pragma: no cover
        text_type = str

    if isinstance(value, text_type):
        return value

    try:
        return text_type(value, "utf-8")
    except (TypeError, ValueError):
        return text_type(value)


def has_selected_reviewer(reviewer_userid):
    """提交工作表前必须已经选择审核人"""
    return bool(normalize_userid(reviewer_userid))


def can_submit_analysis_in_worksheet(has_worksheet, reviewer_userid):
    """工作表内分析项提交前必须先给工作表分配审核人"""
    if not has_worksheet:
        return True
    return has_selected_reviewer(reviewer_userid)


def is_assigned_verifier(current_userid, current_roles, reviewer_userid):
    """判断当前用户是否为被分配的审核人"""
    reviewer_userid = normalize_userid(reviewer_userid)
    current_userid = normalize_userid(current_userid)
    roles = list(current_roles or [])
    if VERIFIER_ROLE not in roles:
        return False
    if not reviewer_userid:
        return False
    return reviewer_userid == current_userid


def collect_verifiable_analyses(worksheets, current_userid):
    """从工作表集合中筛出可审核分析项

    :returns: (selected_analyses, error_messages)
    """
    selected = []
    errors = []
    current_userid = normalize_userid(current_userid)

    for worksheet in list(worksheets or []):
        reviewer_userid = normalize_userid(
            getattr(worksheet, "reviewer_userid", ""))
        title = safe_unicode(getattr(worksheet, "title", "")) or u"(未命名工作表)"

        if reviewer_userid != current_userid:
            errors.append(u"工作表 %s 未分配给当前审核人" % title)
            continue

        analyses = list(worksheet.getAnalyses() or [])
        pending = []
        for analysis in analyses:
            review_state = getattr(analysis, "review_state", "")
            if review_state == PENDING_REVIEW_STATE:
                pending.append(analysis)

        if not pending:
            errors.append(u"工作表 %s 没有可审核的分析项" % title)
            continue

        selected.extend(pending)

    return selected, errors


def can_assign_reviewer(is_worksheet_analyst, has_assign, has_reassign_any):
    """纯判定：当前用户能否修改这张工作表的审核人

    :param is_worksheet_analyst: 当前用户是否为该工作表的被指派分析员
    :param has_assign: 是否有 Assign Reviewer 权限
    :param has_reassign_any: 是否有 Reassign Any Reviewer 权限
    """
    if not has_assign:
        return False
    if is_worksheet_analyst:
        return True
    return bool(has_reassign_any)


def is_reviewer_editable_state(review_state, edit_states):
    """纯判定：该工作表状态下审核人是否可改"""
    if not review_state:
        return False
    return review_state in tuple(edit_states or ())


def should_exclude_submitter(self_verification_flags):
    """纯判定：是否要把未来的提交人从审核人候选中剔除

    自审开关是 analysis 级的（setup 全局 + Analysis Service 级 -1/0/1 覆盖），
    而选审核人在 worksheet 上做 —— 一张工作表混着多个 AS，可能没有统一答案。
    只要存在任一分析项不允许自审，就把提交人排除掉（保守取向）。
    """
    flags = list(self_verification_flags or [])
    if not flags:
        return False
    return not all(flags)


def filter_reviewer_candidates(candidates, excluded_userid):
    """从候选名单中剔除指定用户

    candidates 是 (userid, 显示名) 的序列。excluded_userid 为空时原样返回。
    """
    items = list(candidates or [])
    excluded = normalize_userid(excluded_userid)
    if not excluded:
        return items
    return [item for item in items
            if normalize_userid(item[0]) != excluded]
