# -*- coding: utf-8 -*-

from bika.lims import senaiteMessageFactory as _
from senaite.core.interfaces import IWorksheetLayouts
from zope.interface import implements


class AsGroupedLayout(object):
    """Registers AS-Grouped as a third worksheet layout option."""
    implements(IWorksheetLayouts)

    def getResultLayouts(self):
        return (
            ("as_grouped", _(
                u"as_grouped_view_name",
                default=u"AS-Grouped"
            )),
        )
