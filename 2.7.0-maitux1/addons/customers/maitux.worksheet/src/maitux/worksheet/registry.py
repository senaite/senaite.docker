# -*- coding: utf-8 -*-
"""Global configuration for the AS-Grouped sample view.

Extends the SENAITE registry rather than defining a settings page of our own:
`get_registry_interfaces()` collects every schema that extends
ISenaiteRegistry and the control panel at `/senaite-controlpanel` renders it
automatically, so this shows up next to the stock "Sample View" options with
no further wiring.
"""

from maitux.worksheet import messageFactory as _
from plone.supermodel import model
from senaite.core.registry.schema import ISenaiteRegistry
from zope import schema

# Layout identifiers.  "classic" means: do not interfere, let the sample view
# render the stock ReactJS listing.
LAYOUT_CLASSIC = u"classic"
LAYOUT_AS_GROUPED = u"as_grouped"

DEFAULT_SAMPLE_LAYOUT = LAYOUT_AS_GROUPED


class IMaituxWorksheetRegistry(ISenaiteRegistry):
    """AS-Grouped view settings"""

    model.fieldset(
        "maitux_worksheet",
        label=_(u"AS-Grouped View"),
        description=_(
            u"Default rendering of the analyses listing inside a sample. "
            u"Analysts can still switch per visit; the choice made here is "
            u"what every sample opens with."
        ),
        fields=[
            "sample_analyses_layout",
        ],
    )

    sample_analyses_layout = schema.Choice(
        title=_(u"Sample analyses layout"),
        description=_(
            u"AS-Grouped renders one table per Analysis Service, each showing "
            u"only its own interim fields. Classic keeps the stock single "
            u"table, whose columns are the union of every service's fields."
        ),
        values=[
            LAYOUT_AS_GROUPED,
            LAYOUT_CLASSIC,
        ],
        default=DEFAULT_SAMPLE_LAYOUT,
        required=False,
    )
