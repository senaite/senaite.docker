# -*- coding: utf-8 -*-
"""审核分配相关工作流动作适配器"""

from Products.Archetypes.config import UID_CATALOG
from bika.lims import api
from bika.lims.api.user import get_user_id
from bika.lims.browser.workflow import RequestContextAware
from bika.lims.browser.workflow.analysis import WorkflowActionSubmitAdapter
from bika.lims.interfaces import IWorkflowActionUIDsAdapter
from bika.lims.workflow import doActionFor
from zope.interface import implements

from maitux.reviewerassignment.assignment import get_reviewer_userid
from maitux.reviewerassignment.assignment import set_reviewer_userid
from maitux.reviewerassignment.review_logic import has_selected_reviewer


class WorkflowActionSubmitReviewerAdapter(RequestContextAware):
    """工作表内分析项 submit 时先校验并同步审核人"""

    implements(IWorkflowActionUIDsAdapter)

    def __call__(self, action, uids):
        uids = list(uids or [])
        if not uids:
            return self.redirect(message=u"未找到待提交的分析项。", level="warning")

        reviewer_userid = get_reviewer_userid(self.context)
        if not has_selected_reviewer(reviewer_userid):
            return self.redirect(
                message=u"请先在页面顶部选择审核人并点击 Apply，再执行提交。",
                level="warning")

        analyses = self.get_objects(uids)
        for analysis in analyses:
            # 提交前把当前工作表选定的审核人同步写入分析项，便于后续权限判断与追踪。
            set_reviewer_userid(analysis, reviewer_userid)
            analysis.reindexObject()

        adapter = WorkflowActionSubmitAdapter(self.context, self.request)
        return adapter(action, analyses)

    def get_objects(self, uids):
        brains = api.search(dict(UID=uids), UID_CATALOG)
        return map(api.get_object, brains)


class WorkflowActionVerifyAssignedAdapter(RequestContextAware):
    """审核队列中的批量审核动作"""

    implements(IWorkflowActionUIDsAdapter)

    def __call__(self, action, uids):
        worksheets = self.get_objects(uids)
        if not worksheets:
            return self.redirect(message=u"请先勾选待审核工作表。", level="warning")

        current_userid = get_user_id()
        success_count = 0
        failed_messages = []

        for worksheet in worksheets:
            reviewer_userid = get_reviewer_userid(worksheet)
            worksheet_title = api.get_title(worksheet) or api.get_id(worksheet)
            if reviewer_userid != current_userid:
                failed_messages.append(
                    u"工作表 %s 未分配给当前登录审核人。" % worksheet_title)
                continue

            pending = []
            for analysis in worksheet.getAnalyses() or []:
                if api.get_review_status(analysis) == "to_be_verified":
                    pending.append(analysis)

            if not pending:
                failed_messages.append(
                    u"工作表 %s 没有可审核的分析项。" % worksheet_title)
                continue

            worksheet_failed = False
            for analysis in pending:
                success, message = doActionFor(analysis, "verify")
                if not success:
                    worksheet_failed = True
                    analysis_title = api.get_title(analysis) or api.get_id(analysis)
                    failed_messages.append(
                        u"工作表 %s 的分析 %s 审核失败：%s"
                        % (worksheet_title, analysis_title, message or u"未知错误"))
                    break

            if worksheet_failed:
                continue

            success_count += 1

        if failed_messages:
            message = u"；".join(failed_messages)
            if success_count:
                message = u"已完成 %s 张工作表审核；%s" % (success_count, message)
            return self.redirect(message=message, level="warning")

        return self.redirect(message=u"已完成 %s 张工作表审核。" % success_count)

    def get_objects(self, uids):
        brains = api.search(dict(UID=uids), UID_CATALOG)
        return map(api.get_object, brains)
