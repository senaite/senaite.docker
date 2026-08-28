# -*- coding: utf-8 -*-
"""审核分配 Guard Adapter"""

from bika.lims.api.user import get_user
from bika.lims.api.user import get_user_id
from bika.lims.interfaces import IAnalysis
from senaite.core.interfaces import IWorksheet

from maitux.reviewerassignment.assignment import get_reviewer_userid
from maitux.reviewerassignment.review_logic import (
    can_submit_analysis_in_worksheet,
)
from maitux.reviewerassignment.review_logic import has_selected_reviewer
from maitux.reviewerassignment.review_logic import is_assigned_verifier
from maitux.reviewerassignment.settings import (
    require_reviewer_on_analysis_submit,
)
from maitux.reviewerassignment.settings import (
    require_reviewer_on_worksheet_submit,
)
from maitux.reviewerassignment.settings import (
    restrict_verify_to_assigned_reviewer,
)
from maitux.reviewerassignment.siteinstall import is_installed_in_current_site

ANALYSIS_REVIEW_TRANSITIONS = ("verify", "multi_verify")
ANALYSIS_SUBMIT_TRANSITIONS = ("submit", )


class ReviewerAssignmentGuardAdapter(object):
    """统一处理工作表提交与分析项审核的守卫规则"""

    def __init__(self, context):
        self.context = context

    def guard(self, transition):
        # 本适配器是 for="*" 的进程级注册，所有站点都会调到；只有装了本 addon
        # 的站点才该受这套审核规则约束，其余站点一律放行。详见 siteinstall。
        if not is_installed_in_current_site():
            return True
        if IWorksheet.providedBy(self.context):
            return self.guard_worksheet(transition)
        if IAnalysis.providedBy(self.context):
            return self.guard_analysis(transition)
        return True

    def guard_worksheet(self, transition):
        """工作表 submit 时必须已有审核人（可由站点开关关闭）"""
        if transition != "submit":
            return True
        if not require_reviewer_on_worksheet_submit():
            return True
        reviewer_userid = get_reviewer_userid(self.context)
        return has_selected_reviewer(reviewer_userid)

    def guard_analysis(self, transition):
        """只有被分配的审核人才能审核工作表中的分析项"""
        if transition in ANALYSIS_SUBMIT_TRANSITIONS:
            if not require_reviewer_on_analysis_submit():
                return True
            worksheet = self.context.getWorksheet()
            has_worksheet = worksheet is not None
            reviewer_userid = has_worksheet and get_reviewer_userid(worksheet) or u""
            return can_submit_analysis_in_worksheet(
                has_worksheet, reviewer_userid)

        if transition not in ANALYSIS_REVIEW_TRANSITIONS:
            return True

        # 关闭后不再校验「必须是被指派的那个人」，审核权限回落到 SENAITE 自身的
        # 判断 —— core 的 guard_verify（自审限制、依赖项、需审次数）与 Verify
        # 权限仍然生效，因为 guard_handler 会在适配器全部放行后继续跑它们。
        if not restrict_verify_to_assigned_reviewer():
            return True

        worksheet = self.context.getWorksheet()
        if worksheet is None:
            return True

        reviewer_userid = get_reviewer_userid(worksheet)
        if not reviewer_userid:
            return False

        user_id = get_user_id()
        user = get_user()
        if user is None:
            return False
        roles = user.getRolesInContext(self.context)
        return is_assigned_verifier(user_id, roles, reviewer_userid)
