# -*- coding: utf-8 -*-
from bika.lims import api
from bika.lims import senaiteMessageFactory as _
from bika.lims.browser.workflow import RequestContextAware
from bika.lims.interfaces import IWorkflowActionUIDsAdapter
from zope.interface import implements


class WorkflowActionStockBatchConsumeAdapter(RequestContextAware):
    implements(IWorkflowActionUIDsAdapter)

    def __call__(self, action, uids):
        if not uids:
            return self.redirect(message=_("No items selected."), level="warning")

        base_url = api.get_url(self.context)
        url = "{}/@@stockbatch_consume?uids={}".format(base_url, ",".join(uids))
        return self.request.response.redirect(url)


class WorkflowActionStockBatchDestroyAdapter(RequestContextAware):
    implements(IWorkflowActionUIDsAdapter)

    def __call__(self, action, uids):
        if not uids:
            return self.redirect(message=_("No items selected."), level="warning")

        base_url = api.get_url(self.context)
        url = "{}/@@stockbatch_destroy?uids={}".format(base_url, ",".join(uids))
        return self.request.response.redirect(url)

class WorkflowActionStockBatchReturnAdapter(RequestContextAware):
    implements(IWorkflowActionUIDsAdapter)
    def __call__(self, action, uids):
        if not uids:
            return self.redirect(message=_("No items selected."), level="warning")
        base_url = api.get_url(self.context)
        url = "{}/@@stockbatch_return?uids={}".format(base_url, ",".join(uids))
        return self.request.response.redirect(url)
class WorkflowActionStockBatchSplitAdapter(RequestContextAware):
    implements(IWorkflowActionUIDsAdapter)
    def __call__(self, action, uids):
        if not uids:
            return self.redirect(message=_("No items selected."), level="warning")
        base_url = api.get_url(self.context)
        url = "{}/@@stockbatch_split?uids={}".format(base_url, ",".join(uids))
        return self.request.response.redirect(url)
class WorkflowActionStockBatchStocktakeAdapter(RequestContextAware):
    implements(IWorkflowActionUIDsAdapter)
    def __call__(self, action, uids):
        if not uids:
            return self.redirect(message=_("No items selected."), level="warning")
        base_url = api.get_url(self.context)
        url = "{}/@@stockbatch_stocktake?uids={}".format(base_url, ",".join(uids))
        return self.request.response.redirect(url)
class WorkflowActionStockBatchPrintAdapter(RequestContextAware):
    implements(IWorkflowActionUIDsAdapter)
    def __call__(self, action, uids):
        if not uids:
            return self.redirect(message=_("No items selected."), level="warning")
        base_url = api.get_url(self.context)
        url = "{}/@@stockbatch_print?uids={}".format(base_url, ",".join(uids))
        return self.request.response.redirect(url)

