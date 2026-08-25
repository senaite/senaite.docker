# -*- coding: utf-8 -*-
"""Sample-view analyses viewlets with a layout switch.

Subclasses the stock viewlets and overrides only which listing view renders
the table.  Everything else -- the section title, the collapse toggle, the
`available()` test that hides an empty section -- is inherited untouched, so
this stays in step with senaite.core.
"""

from bika.lims import api
from maitux.worksheet.registry import LAYOUT_AS_GROUPED
from maitux.worksheet.registry import LAYOUT_CLASSIC
from maitux.worksheet.registry import DEFAULT_SAMPLE_LAYOUT
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from senaite.core.browser.viewlets.sampleanalyses import FieldAnalysesViewlet
from senaite.core.browser.viewlets.sampleanalyses import LabAnalysesViewlet
from senaite.core.registry import get_registry_record

# Query string parameter for a per-visit override of the configured default.
LAYOUT_PARAM = "maitux_layout"

# Registry record holding the site-wide default.
REGISTRY_KEY = "sample_analyses_layout"


class GroupedSwitchMixin(object):
    """Adds the AS-Grouped/Classic switch to a sample analyses viewlet."""

    index = ViewPageTemplateFile("templates/sample_analyses_section.pt")

    # Name of the grouped listing view registered for this point of capture.
    grouped_view_name = None

    def get_default_layout(self):
        """Site-wide default, configured in /senaite-controlpanel."""
        try:
            layout = get_registry_record(REGISTRY_KEY,
                                         default=DEFAULT_SAMPLE_LAYOUT)
        except Exception:
            # A missing record must not take the sample view down with it.
            layout = DEFAULT_SAMPLE_LAYOUT
        return layout or DEFAULT_SAMPLE_LAYOUT

    def get_layout(self):
        """Effective layout: an explicit request wins over the default.

        The override is deliberately not persisted.  It is meant for having a
        look at the other rendering, not for changing what the lab works with
        -- that is what the control panel setting is for.
        """
        requested = self.request.get(LAYOUT_PARAM, None)
        if requested in (LAYOUT_AS_GROUPED, LAYOUT_CLASSIC):
            return requested
        return self.get_default_layout()

    def is_grouped(self):
        return self.get_layout() == LAYOUT_AS_GROUPED

    def get_switch_url(self, layout):
        """URL of the current sample with the layout override applied."""
        return "{}?{}={}".format(
            api.get_url(self.sample), LAYOUT_PARAM, layout)

    def get_listing_view(self):
        """Pick the grouped listing when it is the effective layout.

        Falls back to the stock listing if the grouped view cannot be
        resolved, so a broken registration degrades to the native table
        instead of an error page.
        """
        if not self.is_grouped() or not self.grouped_view_name:
            return super(GroupedSwitchMixin, self).get_listing_view()

        request = api.get_request()
        view = api.get_view(
            self.grouped_view_name, context=self.sample, request=request)
        if view is None:
            return super(GroupedSwitchMixin, self).get_listing_view()
        return view

    def contents_table(self):
        """Render the table for the effective layout.

        The stock implementation calls ajax_contents_table(), which returns
        the ReactJS mount point.  The grouped view renders plain HTML through
        contents_table() instead, so the call has to match the view in use.
        """
        view = self.get_listing_view()
        view.update()
        view.before_render()
        if self.is_grouped() and hasattr(view, "as_grouped_table"):
            return view.contents_table()
        return view.ajax_contents_table()


class LabAnalysesGroupedViewlet(GroupedSwitchMixin, LabAnalysesViewlet):
    """Lab analyses section with the layout switch."""

    grouped_view_name = "as_grouped_lab_analyses"


class FieldAnalysesGroupedViewlet(GroupedSwitchMixin, FieldAnalysesViewlet):
    """Field analyses section with the layout switch."""

    grouped_view_name = "as_grouped_field_analyses"
