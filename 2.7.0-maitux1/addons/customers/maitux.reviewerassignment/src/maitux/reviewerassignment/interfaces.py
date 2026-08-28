# -*- coding: utf-8 -*-
"""模块级接口定义"""

from plone.supermodel import model
from senaite.core.interfaces import ISenaiteCore
from zope import schema
from zope.interface import Interface


class IReviewerAssignmentLayer(ISenaiteCore):
    """审核分配浏览器层"""


class IReviewerAssignmentContainer(Interface):
    """审核分配根容器接口"""


class IReviewerAssignmentControlPanelSettings(model.Schema):
    """审核分配的站点级开关

    三条业务规则原来是硬编码的，站点无法调整。这里把它们做成开关，
    默认值与硬编码时的行为完全一致 —— 升级上来的站点行为不变。
    """

    require_reviewer_on_worksheet_submit = schema.Bool(
        title=u"工作表提交前必须已分配审核人",
        description=u"关闭后，未分配审核人的工作表也可以提交。",
        default=True,
        required=False,
    )

    require_reviewer_on_analysis_submit = schema.Bool(
        title=u"工作表内分析项提交前必须已分配审核人",
        description=u"关闭后，工作表未分配审核人时，其中的分析项仍可单独提交。",
        default=True,
        required=False,
    )

    restrict_verify_to_assigned_reviewer = schema.Bool(
        title=u"只有被指派的审核人本人可以审核",
        description=(
            u"关闭后不再校验「必须是被指派的那个人」，审核权限回落到 SENAITE "
            u"自身的判断（Verify 权限、自审限制、依赖项等仍然生效）。"),
        default=True,
        required=False,
    )

    exclude_submitter_from_reviewers = schema.Bool(
        title=u"审核人候选中剔除未来的提交人",
        description=(
            u"依据 SENAITE 的「允许自审」设置：不允许自审时，把工作表的分析员"
            u"从审核人下拉框中剔除，避免选完提交后到审核那一步才失败。"),
        default=True,
        required=False,
    )
