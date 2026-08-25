# -*- coding: utf-8 -*-
"""AS-Grouped layout for the analyses listing inside a Sample.

The stock listing renders every analysis of the sample in one table whose
columns are the *union* of the interim fields of all its services.  With the
kind of services used in pharmaceutical method validation -- where the whole
calculation lives in the interim fields -- that table becomes unreadably wide
and mostly empty: each row only fills the handful of columns belonging to its
own service.

This renders one table per Analysis Service instead, each showing only its own
fields.  Everything else -- saving, recalculation, workflow -- keeps using the
native machinery; `workflow_action_submit` is registered for IAnalysisRequest
as well as for IWorksheet, so the same form target works here unchanged.
"""

from bika.lims import api
from bika.lims.browser.analyses.view import AnalysesView
from maitux.worksheet.browser.views import GroupedRenderingMixin


class SampleAnalysesGroupedBase(GroupedRenderingMixin, AnalysesView):
    """Shared wiring for the per-point-of-capture sample listings.

    Mirrors bika.lims.browser.analysisrequest.tables.LabAnalysesTable, which
    is what the stock viewlet renders; only the layout differs.
    """

    # Point of capture this listing covers; set by the concrete subclasses.
    capture = "lab"

    def __init__(self, context, request):
        super(SampleAnalysesGroupedBase, self).__init__(context, request)

        self.contentFilter.update({
            "getPointOfCapture": self.capture,
            "getAncestorsUIDs": [api.get_uid(context)],
        })

        self.form_id = "%s_%s_analyses_grouped" % (
            api.get_id(context), self.capture)
        self.allow_edit = True
        self.show_workflow_action_buttons = True
        self.show_select_column = True
        self.show_search = False

    def get_redirect_url(self):
        """Back to the sample view once workflow_action is done."""
        return self.context.absolute_url()


class LabAnalysesGroupedView(SampleAnalysesGroupedBase):
    """Lab analyses of a sample, grouped by Analysis Service."""

    capture = "lab"
    view_name = "as_grouped_lab_analyses"


class FieldAnalysesGroupedView(SampleAnalysesGroupedBase):
    """Field analyses of a sample, grouped by Analysis Service."""

    capture = "field"
    view_name = "as_grouped_field_analyses"


# NOTE: the QC analyses section is deliberately left on the stock listing.
# It derives from a different base (QCAnalysesView, selected by
# getQCAnalyses() rather than by point of capture) and is rendered read-only
# -- allow_edit=False, no workflow buttons -- so the wide-table problem this
# layout solves does not arise there.
