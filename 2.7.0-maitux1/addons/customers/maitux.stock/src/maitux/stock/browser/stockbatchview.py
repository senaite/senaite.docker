# -*- coding: utf-8 -*-
from bika.lims import api
from Products.Five.browser import BrowserView


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
            u"create": u"创建",
            u"consume": u"领用",
            u"expire": u"过期",
            u"return": u"归还",
            u"destroy": u"销毁",
            u"split": u"分装",
            u"adjust": u"调整",
            u"stocktake": u"盘存",
        }
        return mapping.get(api.safe_unicode(op), api.safe_unicode(op))
