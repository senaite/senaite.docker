# -*- coding: utf-8 -*-
from bika.lims import api
from bika.lims.browser.workflow import RequestContextAware
from bika.lims.interfaces import IWorkflowActionUIDsAdapter
from zope.interface import implements

from maitux.stock import _
from maitux.stock.browser.stockbatchactions import is_action_allowed_for_uids


def validate_stockbatch_action(adapter, action, uids):
    """在跳转到业务页面前先校验本次选择是否允许该动作。"""
    if not uids:
        return adapter.redirect(message=_("No items selected."), level="warning")

    # 中文注释：前端按钮会做动态收敛，但这里仍保留后端校验，
    # 防止用户手工拼接 URL 或前端状态未及时刷新时绕过限制。
    if is_action_allowed_for_uids(action, uids):
        return None

    return adapter.redirect(
        message=_("Selected batches do not support this action."),
        level="warning",
    )


class WorkflowActionStockBatchConsumeAdapter(RequestContextAware):
    implements(IWorkflowActionUIDsAdapter)

    def __call__(self, action, uids):
        validation = validate_stockbatch_action(self, action, uids)
        if validation is not None:
            return validation

        base_url = api.get_url(self.context)
        url = "{}/@@stockbatch_consume?uids={}".format(base_url, ",".join(uids))
        return self.request.response.redirect(url)


class WorkflowActionStockBatchDestroyAdapter(RequestContextAware):
    implements(IWorkflowActionUIDsAdapter)

    def __call__(self, action, uids):
        validation = validate_stockbatch_action(self, action, uids)
        if validation is not None:
            return validation

        base_url = api.get_url(self.context)
        url = "{}/@@stockbatch_destroy?uids={}".format(base_url, ",".join(uids))
        return self.request.response.redirect(url)

class WorkflowActionStockBatchReturnAdapter(RequestContextAware):
    implements(IWorkflowActionUIDsAdapter)
    def __call__(self, action, uids):
        validation = validate_stockbatch_action(self, action, uids)
        if validation is not None:
            return validation
        base_url = api.get_url(self.context)
        url = "{}/@@stockbatch_return?uids={}".format(base_url, ",".join(uids))
        return self.request.response.redirect(url)
class WorkflowActionStockBatchSplitAdapter(RequestContextAware):
    implements(IWorkflowActionUIDsAdapter)
    def __call__(self, action, uids):
        validation = validate_stockbatch_action(self, action, uids)
        if validation is not None:
            return validation
        base_url = api.get_url(self.context)
        url = "{}/@@stockbatch_split?uids={}".format(base_url, ",".join(uids))
        return self.request.response.redirect(url)
class WorkflowActionStockBatchStocktakeAdapter(RequestContextAware):
    implements(IWorkflowActionUIDsAdapter)
    def __call__(self, action, uids):
        validation = validate_stockbatch_action(self, action, uids)
        if validation is not None:
            return validation
        base_url = api.get_url(self.context)
        url = "{}/@@stockbatch_stocktake?uids={}".format(base_url, ",".join(uids))
        return self.request.response.redirect(url)
class WorkflowActionStockBatchPrintAdapter(RequestContextAware):
    implements(IWorkflowActionUIDsAdapter)
    def __call__(self, action, uids):
        validation = validate_stockbatch_action(self, action, uids)
        if validation is not None:
            return validation
        base_url = api.get_url(self.context)
        url = "{}/@@stockbatch_print?uids={}".format(base_url, ",".join(uids))
        return self.request.response.redirect(url)
