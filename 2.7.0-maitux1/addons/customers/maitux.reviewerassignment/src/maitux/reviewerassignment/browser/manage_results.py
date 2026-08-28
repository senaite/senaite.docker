# -*- coding: utf-8 -*-
"""审核分配版工作表结果录入页"""

from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from bika.lims import api
from senaite.core.browser.worksheets.worksheet.manage_results import (
    ManageResultsView as BaseManageResultsView,
)

from bika.lims.api.security import check_permission
from bika.lims.api.user import get_user_id

from maitux.reviewerassignment.assignment import get_member_fullname
from maitux.reviewerassignment.assignment import get_reviewer_userid
from maitux.reviewerassignment.assignment import iter_reviewer_options
from maitux.reviewerassignment.assignment import set_reviewer_userid
from maitux.reviewerassignment.config import REVIEWER_EDIT_STATES
from maitux.reviewerassignment.permissions import AssignReviewer
from maitux.reviewerassignment.permissions import ReassignAnyReviewer
from maitux.reviewerassignment.review_logic import can_assign_reviewer
from maitux.reviewerassignment.review_logic import is_reviewer_editable_state
from maitux.reviewerassignment.review_logic import normalize_userid


class ManageResultsView(BaseManageResultsView):
    """在原管理结果页头部增加审核人分配入口"""

    template = ViewPageTemplateFile("templates/manage_results.pt")

    def __call__(self):
        if self.request.get("reviewer_assignment_apply"):
            self.handle_reviewer_assignment()
        return super(ManageResultsView, self).__call__()

    def is_worksheet_analyst(self):
        """当前用户是否为本工作表的被指派分析员

        归属判据取 getAnalyst()，与 SENAITE 自己的 guard_submit
        （提交人必须是被指派分析员）同一套语义，且与「谁创建了工作表」无关 ——
        严格实验室和研发实验室两种流程下都成立。
        """
        getter = getattr(self.context, "getAnalyst", None)
        if not callable(getter):
            return False
        try:
            analyst = getter() or u""
        except Exception:
            return False
        analyst = normalize_userid(analyst)
        if not analyst:
            return False
        return analyst == normalize_userid(get_user_id())

    def can_assign_reviewer(self):
        """能否修改本工作表的审核人（供模板与写入路径共用）

        不复用 senaite.core 的 is_assignment_allowed —— 那个只看 ManageWorksheets，
        没有归属判断。一旦站点把 RestrictWorksheetManagement 改成 False
        （让实验员能建工作表），SENAITE 会自动把 ManageWorksheets 授予 Analyst，
        实验员立刻能改任意工作表的审核人。归属边界只能由本 addon 用代码提供。
        """
        if not is_reviewer_editable_state(
                api.get_review_status(self.context), REVIEWER_EDIT_STATES):
            return False
        return can_assign_reviewer(
            self.is_worksheet_analyst(),
            check_permission(AssignReviewer, self.context),
            check_permission(ReassignAnyReviewer, self.context))

    def handle_reviewer_assignment(self):
        """处理审核人 Apply 动作"""
        # 校验必须在写入路径上，不能只靠模板控制显隐 —— 模板管渲染，
        # 构造请求可以绕过它。这里是唯一的写入入口。
        if not self.can_assign_reviewer():
            self.add_status_message(
                u"没有权限修改本工作表的审核人，或当前状态不允许修改。",
                "error")
            return

        reviewer_userid = self.request.form.get("reviewer_userid", u"")
        reviewer_userid = api.safe_unicode(reviewer_userid).strip()
        if not reviewer_userid:
            self.add_status_message(u"请选择审核人后再点击 Apply。", "warning")
            return

        # 候选名单本身已按站点自审设置过滤，这里再挡一次直接构造请求的情况。
        allowed = [item[0] for item in self.get_reviewer_options()]
        if reviewer_userid not in allowed:
            self.add_status_message(
                u"该用户不在本工作表的可选审核人名单内。", "error")
            return

        set_reviewer_userid(self.context, reviewer_userid)
        self.context.reindexObject(idxs=["getReviewerUserId"])
        self.add_status_message(u"审核人已保存。", "info")

    def get_reviewer_options(self):
        """返回审核人下拉框选项"""
        return list(iter_reviewer_options(self.context))

    def get_selected_reviewer(self):
        """返回当前已分配审核人"""
        value = self.request.form.get("reviewer_userid")
        if value is not None:
            return api.safe_unicode(value).strip()
        return get_reviewer_userid(self.context)

    def get_selected_reviewer_title(self):
        """返回当前已分配审核人显示名"""
        reviewer_userid = get_reviewer_userid(self.context)
        return get_member_fullname(self.context, reviewer_userid)
