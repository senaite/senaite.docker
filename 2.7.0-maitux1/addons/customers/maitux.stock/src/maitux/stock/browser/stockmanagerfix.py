# -*- coding: utf-8 -*-
from Products.Five.browser import BrowserView
from bika.lims import api

from maitux.stock import _


class StockStructureFixView(BrowserView):
    def __call__(self):
        ctx = self.context
        if api.get_portal_type(ctx) != "StockManager":
            self.context.plone_utils.addPortalMessage(_("Not a Stock Manager."), "warning")
            return self.request.response.redirect(api.get_url(ctx))

        # Rename StockManager title
        try:
            if getattr(ctx, "Title", None) and ctx.Title() != "Stockinventory":
                ctx.setTitle("Stockinventory")
                ctx.reindexObject()
        except Exception:
            pass

        # Remove Dynamic section
        try:
            if "stock_dynamic" in ctx.objectIds():
                ctx.manage_delObjects(["stock_dynamic"])
        except Exception:
            pass

        # Rename Types section title
        try:
            types_folder = ctx.get("stock_types")
            if types_folder and getattr(types_folder, "Title", None):
                if types_folder.Title() != "Stock Types stock":
                    types_folder.setTitle("Stock Types stock")
                    types_folder.reindexObject()
        except Exception:
            pass

        # Rename Stock folder title
        try:
            stock_folder = ctx.get("stock")
            if stock_folder and getattr(stock_folder, "Title", None):
                if stock_folder.Title() != "Stock Item":
                    stock_folder.setTitle("Stock Item")
                    stock_folder.reindexObject()
        except Exception:
            pass

        self.context.plone_utils.addPortalMessage(_("Changes applied."), "info")
        return self.request.response.redirect(api.get_url(ctx))
