# -*- coding: utf-8 -*-
import collections
from decimal import Decimal

from bika.lims import api
from bika.lims.utils import get_link
from senaite.app.listing import ListingView
from senaite.core.api import dtime
from senaite.core.i18n import translate

from maitux.stock import _
from maitux.stock.stockbatchexpiry import REVIEW_STATE_DESTROYED

class LowStockBatchesView(ListingView):
    def __init__(self, context, request):
        super(LowStockBatchesView, self).__init__(context, request)

        self.title = translate(_(
            u"listing_lowstock_title",
            default=u"Low Quantity"
        ))
        self.icon = api.get_icon(context, html_tag=False)
        self.catalog = "portal_catalog"
        self.show_search = True
        self.show_select_column = False

        self.stock_manager = self._get_stock_manager(context)
        self.batches_container = self.stock_manager.get("stock_batches") if self.stock_manager else None
        container_path = api.get_path(self.batches_container) if self.batches_container else api.get_path(context)

        self.contentFilter = {
            "portal_type": "StockBatch",
            "sort_on": "created",
            "sort_order": "descending",
            "path": {
                "query": container_path,
                "depth": 1,
            },
        }

        self.context_actions = {}

        self.columns = collections.OrderedDict((
            ("batch_id", {"title": _(u"listing_stockbatches_column_batch_id", default=u"Batch ID"), "toggle": True}),
            ("stock", {"title": _(u"listing_stockbatches_column_stock", default=u"Stock"), "toggle": True}),
            ("supplier", {"title": _(u"listing_stockbatches_column_supplier", default=u"Supplier"), "toggle": True}),
            ("current_amount", {"title": _(u"listing_stockbatches_column_current_amount", default=u"Current Amount"), "toggle": True}),
            ("low_quantity_threshold", {"title": _(u"listing_lowstock_column_threshold", default=u"Threshold"), "toggle": True}),
            ("below_by", {"title": _(u"listing_lowstock_column_below_by", default=u"Below By"), "toggle": True}),
            ("unit", {"title": _(u"listing_stockbatches_column_unit", default=u"Unit"), "toggle": True}),
            ("expiry_date", {"title": _(u"listing_stockbatches_column_expiry_date", default=u"Expiry Date"), "toggle": True}),
            ("status", {"title": _(u"listing_stockbatches_column_status", default=u"Status"), "toggle": True}),
        ))
        columns = list(self.columns.keys())

        self.review_states = [
            {
                "id": "default",
                "title": translate(_(
                    u"listing_lowstock_title",
                    default=u"Low Quantity"
                )),
                "contentFilter": {},
                "columns": columns,
            }
        ]

    def get_catalog_query(self, **kw):
        query = super(LowStockBatchesView, self).get_catalog_query(**kw)
        searchterm = kw.get("searchterm", "") or self.request.get("searchterm", "") or ""
        searchterm = api.safe_unicode(searchterm).strip()
        if searchterm:
            query["Title"] = searchterm
        return query

    def _get_stock_manager(self, context):
        obj = context
        while obj and api.is_object(obj):
            if api.get_portal_type(obj) == "StockManager":
                return obj
            obj = api.get_parent(obj)
        return None

    def _first_uid(self, value):
        if not value:
            return ""
        if isinstance(value, (list, tuple)):
            value = value[0] if value else ""
        value = api.safe_unicode(value)
        parts = value.splitlines()
        return parts[0] if parts else ""

    def _to_decimal(self, value, default="0.00"):
        try:
            return Decimal(value)
        except Exception:
            return Decimal(default)

    def _format_dt(self, value):
        if not value:
            return ""
        try:
            ansi = dtime.to_ansi(value, show_time=True)
            if not ansi:
                return ""
            return "{}-{}-{} {}:{}:{}".format(
                ansi[0:4], ansi[4:6], ansi[6:8],
                ansi[8:10], ansi[10:12], ansi[12:14],
            )
        except Exception:
            return ""

    def _format_amount(self, value):
        try:
            val = Decimal(value)
            return "{:.2f}".format(val)
        except Exception:
            return "{}".format(value if value is not None else "0")

    def _is_low(self, batch):
        if api.get_review_status(batch) == REVIEW_STATE_DESTROYED:
            return False
        thr = getattr(batch, "low_quantity_threshold", None)
        if thr in (None, ""):
            return False
        thr = self._to_decimal(thr, default="0.00")
        if thr <= Decimal("0.00"):
            return False
        cur = getattr(batch, "current_amount", None)
        cur = self._to_decimal(cur, default="0.00")
        return cur < thr

    def folderitem(self, obj, item, index):
        item = super(LowStockBatchesView, self).folderitem(obj, item, index)
        if not item:
            return None

        batch = api.get_object(obj)
        if not self._is_low(batch):
            return None

        batch_id = getattr(batch, "batch_id", "") or ""
        item["batch_id"] = batch_id

        stock_uid = self._first_uid(getattr(batch, "stock", "") or "")
        stock = api.get_object_by_uid(stock_uid, default=None) if stock_uid else None
        item["stock"] = api.get_title(stock) if stock else ""

        supplier_uid = self._first_uid(getattr(batch, "supplier", "") or "")
        supplier = api.get_object_by_uid(supplier_uid, default=None) if supplier_uid else None
        item["supplier"] = api.get_title(supplier) if supplier else ""

        cur_val = self._to_decimal(getattr(batch, "current_amount", None), default="0.00")
        thr_val = self._to_decimal(getattr(batch, "low_quantity_threshold", None), default="0.00")

        item["current_amount"] = self._format_amount(cur_val)
        item["low_quantity_threshold"] = self._format_amount(thr_val)
        item["below_by"] = self._format_amount(thr_val - cur_val)

        unit_uid = self._first_uid(getattr(batch, "unit", "") or "")
        unit = api.get_object_by_uid(unit_uid, default=None) if unit_uid else None
        if unit:
            item["unit"] = api.get_title(unit)
        else:
            item["unit"] = api.safe_unicode(getattr(batch, "unit", "") or "").strip()

        expiry = getattr(batch, "expiry_date", None)
        item["expiry_date"] = self._format_dt(expiry) if expiry else ""

        item["status"] = api.get_review_status(batch) or ""

        item["replace"]["batch_id"] = get_link(
            href=api.get_url(batch),
            value=batch_id or api.get_title(batch),
            csrf=False,
        )

        return item
