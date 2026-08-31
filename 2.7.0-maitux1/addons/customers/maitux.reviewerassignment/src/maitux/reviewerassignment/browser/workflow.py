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
from maitux.reviewerassignment.review_logic import has_selected_reviewer

try:
    from maitux.esignature.browser.workflow import maybe_redirect_signature_prompt_for_action
except ImportError:
    maybe_redirect_signature_prompt_for_action = None


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

        # 这里曾经把工作表的审核人复制一份写到每个分析项的 annotation 上。
        # 那份副本从来没有被任何代码读过 —— guard_analysis 读的始终是工作表上的值，
        # 而改工作表审核人时副本也不会跟着更新。留着只是个数据不一致的隐患：
        # 哪天有人改成读分析项那份，就会冒出「改了没生效」的诡异 bug。
        # 审核人是工作表级的属性，一张工作表一个审核人，不需要按分析项存。
        analyses = self.get_objects(uids)
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
        all_pending_analyses = []
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
            
            all_pending_analyses.extend(pending)

        if failed_messages and not all_pending_analyses:
            message = u"；".join(failed_messages)
            return self.redirect(message=message, level="warning")

        # ADD(2026-08-30) - 对接电子签名插件。
        if maybe_redirect_signature_prompt_for_action:
            analysis_uids = [api.get_uid(a) for a in all_pending_analyses]
            response = maybe_redirect_signature_prompt_for_action(
                self.context,
                self.request,
                "verify",
                analysis_uids,
                back_url=self.back_url
            )
            if response:
                return response

        # 如果不需要签名或插件未安装，则执行直接审核逻辑。
        success_count = 0
        processed_worksheets = set()

        for analysis in all_pending_analyses:
            # 找到分析项对应的工作表用于计数和消息显示
            worksheet = None
            for ref in analysis.getBackReferences("WorksheetAnalysis"):
                worksheet = ref
                break
            
            success, message = doActionFor(analysis, "verify")
            if not success:
                worksheet_title = api.get_title(worksheet) or api.get_id(worksheet)
                analysis_title = api.get_title(analysis) or api.get_id(analysis)
                failed_messages.append(
                    u"工作表 %s 的分析 %s 审核失败：%s"
                    % (worksheet_title, analysis_title, message or u"未知错误"))
                continue
            
            if worksheet and worksheet not in processed_worksheets:
                processed_worksheets.add(worksheet)
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
