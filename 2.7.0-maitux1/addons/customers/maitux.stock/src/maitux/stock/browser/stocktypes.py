# -*- coding: utf-8 -*-
import collections

from bika.lims import api
from bika.lims.utils import get_link
from senaite.app.listing import ListingView
from senaite.core.catalog import SETUP_CATALOG
from senaite.core.i18n import translate

from maitux.stock import _


class StockTypesView(ListingView):
    def __init__(self, context, request):
        super(StockTypesView, self).__init__(context, request)

        self.catalog = SETUP_CATALOG
        self.contentFilter = {
            "portal_type": "StockType",
            "sort_on": "sortable_title",
            "sort_order": "ascending",
            "path": {
                "query": api.get_path(self.context),
                "depth": 1,
            },
        }

        self.context_actions = {
            _(u"listing_stocktypes_action_add", default=u"Add"): {
                "url": "++add++StockType",
                "permission": "cmf.AddPortalContent",
                "icon": "senaite_theme/icon/plus",
            }
        }

        self.title = translate(_(
            u"listing_stocktypes_title",
            default=u"Stock Types"
        ))
        self.show_select_column = True

        self.columns = collections.OrderedDict((
            ("Title", {
                "title": _(u"listing_stocktypes_column_title", default=u"Title"),
                "index": "sortable_title",
            }),
            ("Description", {
                "title": _(u"listing_stocktypes_column_description", default=u"Description"),
                "toggle": True,
            }),
        ))

        self.review_states = [
            {
                "id": "default",
                "title": _(u"listing_state_active", default=u"Active"),
                "contentFilter": {"is_active": True},
                "columns": self.columns.keys(),
            }, {
                "id": "inactive",
                "title": _(u"listing_state_inactive", default=u"Inactive"),
                "contentFilter": {"is_active": False},
                "columns": self.columns.keys(),
            }, {
                "id": "all",
                "title": _(u"listing_state_all", default=u"All"),
                "contentFilter": {},
                "columns": self.columns.keys(),
            },
        ]

    def folderitem(self, obj, item, index):
        item = super(StockTypesView, self).folderitem(obj, item, index)
        obj = api.get_object(obj)
        item["replace"]["Title"] = get_link(
            href=api.get_url(obj),
            value=api.get_title(obj),
            csrf=False,
        )
        return item
