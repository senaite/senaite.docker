# -*- coding: utf-8 -*-
import json

from Products.Five.browser import BrowserView
from bika.lims import api


class StockQuantityJSON(BrowserView):
    def resolve_stock(self, value):
        if not value:
            return None
        if isinstance(value, (list, tuple)):
            value = value[0] if value else ""
        parts = api.safe_unicode(value).splitlines()
        value = parts[0].strip() if parts else ""
        if not value:
            return None

        if api.is_uid(value):
            stock = api.get_object_by_uid(value, default=None)
            if api.is_object(stock):
                return stock

        portal_catalog = api.get_tool("portal_catalog")
        queries = [
            {"portal_type": "Stock", "sortable_title": value},
            {"portal_type": "Stock", "Title": value},
            {"portal_type": "Stock", "id": value},
        ]
        for query in queries:
            try:
                brains = portal_catalog(**query)
                if brains:
                    return api.get_object(brains[0])
            except Exception:
                continue
        return None

    def __call__(self):
        self.request.response.setHeader("Content-Type", "application/json")
        stock_value = self.request.get("stock_uid") or self.request.get("uid") or ""
        stock = self.resolve_stock(stock_value)
        if not api.is_object(stock):
            return json.dumps({"quantity": ""})
        qty = getattr(stock, "quantity", None)
        if qty is None:
            return json.dumps({"quantity": ""})
        try:
            qty = api.safe_unicode(qty)
        except Exception:
            qty = str(qty)
        return json.dumps({"quantity": qty})
