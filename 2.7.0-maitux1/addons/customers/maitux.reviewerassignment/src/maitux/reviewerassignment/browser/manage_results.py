# -*- coding: utf-8 -*-
"""审核分配版工作表结果录入页"""

from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from bika.lims import api
from senaite.core.browser.worksheets.worksheet.manage_results import (
    ManageResultsView as BaseManageResultsView,
)

from maitux.reviewerassignment.assignment import get_member_fullname
from maitux.reviewerassignment.assignment import get_reviewer_userid
from maitux.reviewerassignment.assignment import iter_reviewer_options
from maitux.reviewerassignment.assignment import set_reviewer_userid


class ManageResultsView(BaseManageResultsView):
    """在原管理结果页头部增加审核人分配入口"""

    template = ViewPageTemplateFile("templates/manage_results.pt")

    def __call__(self):
        if self.request.get("reviewer_assignment_apply"):
            self.handle_reviewer_assignment()
        return super(ManageResultsView, self).__call__()

    def handle_reviewer_assignment(self):
        """处理审核人 Apply 动作"""
        reviewer_userid = self.request.form.get("reviewer_userid", u"")
        reviewer_userid = api.safe_unicode(reviewer_userid).strip()
        if not reviewer_userid:
            self.add_status_message(u"请选择审核人后再点击 Apply。", "warning")
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
