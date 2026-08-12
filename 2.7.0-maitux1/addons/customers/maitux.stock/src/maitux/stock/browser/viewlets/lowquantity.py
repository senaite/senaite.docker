# -*- coding: utf-8 -*-
from decimal import Decimal

from bika.lims import api
from plone.app.layout.viewlets import ViewletBase
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile


class StockBatchesLowQuantityViewlet(ViewletBase):
    index = ViewPageTemplateFile("templates/stock_low_quantity_viewlet.pt")

    def __init__(self, context, request, view, manager=None):
        super(StockBatchesLowQuantityViewlet, self).__init__(
            context, request, view, manager=manager
        )
        self._items = []

    def _to_decimal(self, value, default="0.00"):
        try:
            return Decimal(value)
        except Exception:
            return Decimal(default)

    def get_low_batches(self):
        context = self.context
        catalog = api.get_tool("portal_catalog")
        brains = catalog(
            portal_type="StockBatch",
            path={"query": api.get_path(context), "depth": 1},
        )
        items = []
        for brain in brains:
            batch = brain.getObject()
            if api.get_review_status(batch) == "destroyed":
                continue
            thr = getattr(batch, "low_quantity_threshold", None)
            if thr in (None, ""):
                continue
            thr = self._to_decimal(thr, default="0.00")
            if thr <= Decimal("0.00"):
                continue
            cur = getattr(batch, "current_amount", None)
            cur = self._to_decimal(cur, default="0.00")
            if cur < thr:
                title = getattr(batch, "batch_id", "") or api.get_title(batch)
                items.append({
                    "uid": api.get_uid(batch),
                    "title": title,
                    "url": api.get_url(batch),
                    "current": cur,
                    "threshold": thr,
                })
        items.sort(key=lambda i: api.safe_unicode(i.get("title", "")))
        return items

    def available(self):
        return True

    def render(self):
        try:
            self._items = self.get_low_batches()
            if not self._items:
                return ""
            return self.index()
        except Exception:
            return ""
