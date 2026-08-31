# -*- coding: utf-8 -*-
import collections

from bika.lims import api
from bika.lims.utils import get_link
from senaite.app.listing import ListingView
from senaite.core.api import dtime
from senaite.core.catalog import SETUP_CATALOG
from senaite.core.i18n import translate

from maitux.stock import _


class StockItemsView(ListingView):
    def __init__(self, context, request):
        super(StockItemsView, self).__init__(context, request)

        self.catalog = "portal_catalog"
        self.contentFilter = {
            "portal_type": "Stock",
            "sort_on": "created",
            "sort_order": "reverse",
            "path": {
                "query": api.get_path(self.context),
                "depth": 1,
            },
        }

        self.context_actions = {
            _(u"listing_stockitems_action_add", default=u"Add"): {
                "url": "++add++Stock",
                "permission": "cmf.AddPortalContent",
                "icon": "senaite_theme/icon/plus",
            }
        }

        self.title = translate(_(
            u"listing_stockitems_title",
            default=u"Stock Item"
        ))
        self.show_select_column = True

        self.columns = collections.OrderedDict((
            ("number", {
                "title": _(u"listing_stockitems_column_number", default=u"Number"),
                "index": "sortable_title"}),
            ("stock_type", {
                "title": _(u"listing_stockitems_column_type", default=u"Type"),
                "toggle": True}),
            ("sample_matrix", {
                "title": _(u"listing_stockitems_column_name", default=u"Name"),
                "toggle": True}),
            ("supplier", {
                "title": _(u"listing_stockitems_column_supplier", default=u"Supplier"),
                "toggle": True}),
            ("quantity", {
                "title": _(u"listing_stockitems_column_quantity", default=u"Quantity"),
                "toggle": True,
            }),
            ("unit", {
                "title": _(u"listing_stockitems_column_unit", default=u"Unit"),
                "toggle": True,
            }),
            ("location", {
                "title": _(u"listing_stockitems_column_location", default=u"Location"),
                "toggle": True,
            }),
            ("expiry_date", {
                "title": _(u"listing_stockitems_column_expiry", default=u"Expiry Date"),
                "toggle": True,
            }),
        ))

        self.review_states = [
            {
                "id": "default",
                "title": _(u"listing_state_all", default=u"All"),
                "contentFilter": {},
                "columns": self.columns.keys(),
            },
        ]

    def folderitem(self, obj, item, index):
        item = super(StockItemsView, self).folderitem(obj, item, index)
        obj = api.get_object(obj)
        fields = api.get_fields(obj)

        def resolve_by_uid(uid):
            if not api.is_uid(uid):
                return None
            for catalog_id in ("uid_catalog", SETUP_CATALOG, "portal_catalog"):
                try:
                    catalog = api.get_tool(catalog_id)
                    brains = catalog(UID=uid)
                    if brains:
                        return api.get_object(brains[0])
                except Exception:
                    continue
            return None

        def get_ref_title(fieldname):
            field = fields.get(fieldname)
            if not field:
                return ""
            try:
                raw = field.get_raw(obj)
            except Exception:
                raw = getattr(obj, fieldname, None)
            if raw is None:
                return ""
            if not isinstance(raw, (list, tuple)):
                raw = [raw]
            titles = []
            for uid in filter(None, raw):
                if api.is_object(uid):
                    title = api.get_title(uid)
                else:
                    ref = resolve_by_uid(uid)
                    title = api.get_title(ref) if api.is_object(ref) else ""
                if title:
                    titles.append(title)
            return ", ".join(titles)

        def format_date(value):
            if not value:
                return ""
            try:
                ansi = dtime.to_ansi(value, show_time=True)
                if ansi:
                    return "{}-{}-{} {}:{}:{}".format(
                        ansi[0:4], ansi[4:6], ansi[6:8],
                        ansi[8:10], ansi[10:12], ansi[12:14],
                    )
            except Exception:
                pass
            return ""

        number = getattr(obj, "number", "") or ""
        item["number"] = number
        item["stock_type"] = get_ref_title("stock_type")
        item["sample_matrix"] = get_ref_title("sample_matrix")
        item["supplier"] = get_ref_title("supplier")
        item["quantity"] = getattr(obj, "quantity", "") or ""
        item["unit"] = get_ref_title("unit")
        item["location"] = get_ref_title("location")
        item["expiry_date"] = format_date(getattr(obj, "expiry_date", None))

        item["replace"]["number"] = get_link(
            href=api.get_url(obj),
            value=number or api.get_title(obj),
            csrf=False,
        )
        return item
