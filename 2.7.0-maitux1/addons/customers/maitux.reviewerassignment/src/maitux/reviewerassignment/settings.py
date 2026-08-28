# -*- coding: utf-8 -*-
"""站点级开关的读取

registry 记录只在装了本 addon 的站点存在。未安装站点、或记录尚未注册时，
一律回落到接口里的默认值 —— 与硬编码时期的行为完全一致，升级不改变行为。

读取失败一律回落默认值，绝不抛异常：这些开关会在 guard 求值路径上被读到，
一个异常就能把整条工作流卡死。
"""

from plone import api as ploneapi

from maitux.reviewerassignment.config import REGISTRY_PREFIX


DEFAULTS = {
    "require_reviewer_on_worksheet_submit": True,
    "require_reviewer_on_analysis_submit": True,
    "restrict_verify_to_assigned_reviewer": True,
    "exclude_submitter_from_reviewers": True,
}


def get_setting(name):
    """读取一个开关，取不到时回落到默认值"""
    default = DEFAULTS.get(name, True)
    key = "%s.%s" % (REGISTRY_PREFIX, name)
    try:
        value = ploneapi.portal.get_registry_record(key, default=default)
    except Exception:
        return default
    if value is None:
        return default
    return bool(value)


def require_reviewer_on_worksheet_submit():
    return get_setting("require_reviewer_on_worksheet_submit")


def require_reviewer_on_analysis_submit():
    return get_setting("require_reviewer_on_analysis_submit")


def restrict_verify_to_assigned_reviewer():
    return get_setting("restrict_verify_to_assigned_reviewer")


def exclude_submitter_from_reviewers():
    return get_setting("exclude_submitter_from_reviewers")
