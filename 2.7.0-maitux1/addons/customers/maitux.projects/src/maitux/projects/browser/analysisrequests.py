# -*- coding: utf-8 -*-
from bika.lims import api
from senaite.core.browser.batches.samples import SamplesView as BaseView


class ProjectAnalysisRequestsView(BaseView):
    """Listing of the Analysis Requests linked to the current Project.

    Copied from ``senaite.core.browser.batches.samples.SamplesView``
    (the Batches "Analysis Requests" page), filtering by the ``ProjectNo``
    extension field of the Analysis Requests (stores the Project UID)
    instead of ``getBatchUID``.
    """

    def __init__(self, context, request):
        super(ProjectAnalysisRequestsView, self).__init__(context, request)
        self.contentFilter = {
            "portal_type": "AnalysisRequest",
            "ProjectNo": api.get_uid(self.context),
            "sort_on": "created",
            "sort_order": "reverse",
            "isRootAncestor": True,  # only root ancestors
        }
