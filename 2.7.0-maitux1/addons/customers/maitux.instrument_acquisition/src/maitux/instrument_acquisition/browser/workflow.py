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

