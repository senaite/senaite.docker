# -*- coding: utf-8 -*-
from bika.lims import api
from bika.lims import senaiteMessageFactory as _
from bika.lims.browser.workflow import RequestContextAware
from bika.lims.interfaces import IWorkflowActionUIDsAdapter
from zope.interface import implements


class WorkflowActionInstrumentAcquisitionDebugAdapter(RequestContextAware):
    implements(IWorkflowActionUIDsAdapter)

    def __call__(self, action, uids):
        if not uids:
            return self.redirect(message=_("No items selected."), level="warning")

        uid = uids[0]
        if len(uids) > 1:
            self.add_status_message(
                _("Multiple items selected. Opening debug for the first one only."),
                level="warning",
            )

        setup = api.get_senaite_setup()
        setup_url = api.get_url(setup) if setup else api.get_url(self.context)
        url = "{}/@@instrument_acquisition_debug?uid={}".format(setup_url, uid)
        return self.request.response.redirect(url)


class WorkflowActionInstrumentAcquisitionAdapter(RequestContextAware):
    """工作表列表底部工具栏「仪器采集」动作：只能单选，进入采集页"""

    implements(IWorkflowActionUIDsAdapter)

    def __call__(self, action, uids):
        uids = list(uids or [])
        if not uids:
            return self.redirect(
                message=u"请先勾选一个工作表。", level="warning")
        if len(uids) > 1:
            return self.redirect(
                message=u"仪器采集只能单选一个工作表，请只勾选一项。",
                level="warning")

        try:
            worksheet = api.get_object(uids[0])
        except Exception:
            worksheet = None
        if not api.is_object(worksheet) or \
                api.get_portal_type(worksheet) != "Worksheet":
            return self.redirect(
                message=u"请先勾选一个工作表。", level="warning")

        url = "{}/@@worksheet_instrument_acquisition".format(
            api.get_url(worksheet))
        return self.request.response.redirect(url)

