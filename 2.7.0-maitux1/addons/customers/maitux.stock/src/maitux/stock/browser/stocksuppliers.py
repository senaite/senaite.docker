# -*- coding: utf-8 -*-
import json

from Products.Five.browser import BrowserView
from bika.lims import api
from senaite.core.catalog import SETUP_CATALOG


class StockSuppliersJSON(BrowserView):
    def resolve_by_uid(self, uid):
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

    def resolve_stock(self, value):
        if not value:
            return None
        if isinstance(value, (list, tuple)):
            value = value[0] if value else ""
        parts = api.safe_unicode(value).splitlines()
        value = parts[0].strip() if parts else ""
        if not value:
            return None

        stock = self.resolve_by_uid(value)
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
        stock_uid = self.request.get("stock_uid") or self.request.get("uid")
        stock = self.resolve_stock(stock_uid)
        if not api.is_object(stock):
            return json.dumps([])

        fields = api.get_fields(stock)
        supplier_field = fields.get("supplier")
        supplier_uids = []
        if supplier_field:
            try:
                supplier_uids = supplier_field.get_raw(stock) or []
            except Exception:
                supplier_uids = []
        if not isinstance(supplier_uids, (list, tuple)):
            supplier_uids = [supplier_uids]
        supplier_uids = filter(None, supplier_uids)

        data = []
        for uid in supplier_uids:
            sup = self.resolve_by_uid(uid)
            if not api.is_object(sup):
                continue
            data.append({
                "uid": api.get_uid(sup),
                "title": api.get_title(sup) or api.get_id(sup),
            })
        return json.dumps(data)
