# -*- coding: utf-8 -*-
from bika.lims import api
from Products.Five.browser import BrowserView

from maitux.stock import _


class StockBatchView(BrowserView):
    def review_state(self):
        return api.get_review_status(self.context) or ""

    def as_title(self, uid):
        if not uid:
            return ""
        if isinstance(uid, (list, tuple)):
            uid = uid[0] if uid else ""
            if not uid:
                return ""
        uid = api.safe_unicode(uid)
        parts = uid.splitlines()
        uid = parts[0] if parts else ""
        obj = api.get_object_by_uid(uid, default=None) if uid else None
        return api.get_title(obj) if obj else ""

    def usage_records(self):
        return getattr(self.context, "usage_records", []) or []

    def operation_label(self, op):
        mapping = {
            u"create": _(u"operation_create", default=u"Create"),
            u"consume": _(u"operation_consume", default=u"Consume"),
            u"expire": _(u"operation_expire", default=u"Expire"),
            u"return": _(u"operation_return", default=u"Return"),
            u"destroy": _(u"operation_destroy", default=u"Destroy"),
            u"split": _(u"operation_split", default=u"Split"),
            u"adjust": _(u"operation_adjust", default=u"Adjust"),
            u"stocktake": _(u"operation_stocktake", default=u"Stocktake"),
        }
        return mapping.get(api.safe_unicode(op), api.safe_unicode(op))
