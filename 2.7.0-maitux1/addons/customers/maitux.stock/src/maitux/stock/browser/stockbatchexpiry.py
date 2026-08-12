# -*- coding: utf-8 -*-
from Products.Five.browser import BrowserView
from bika.lims import api
from plone.protect.interfaces import IDisableCSRFProtection
from zope.interface import alsoProvides

from maitux.stock.stockbatchexpiry import sync_expired_batches


class StockBatchExpirySyncView(BrowserView):
    """供计划任务调用的过期批次同步入口。"""

    def __call__(self):
        # 定时任务通常通过 curl / wget 调用，这里关闭 CSRF 校验。
        alsoProvides(self.request, IDisableCSRFProtection)
        dry_run = bool(int(self.request.get("dry_run", 0) or 0))
        limit = self.request.get("limit", "")
        try:
            limit = int(limit) if limit not in (None, "") else None
        except Exception:
            limit = None

        result = sync_expired_batches(
            self.context,
            limit=limit,
            dry_run=dry_run,
        )
        self.request.response.setHeader("Content-Type", "text/plain; charset=utf-8")
        lines = [
            u"checked={}".format(result.get("checked", 0)),
            u"expired={}".format(result.get("expired", 0)),
            u"status_synced={}".format(result.get("status_synced", 0)),
            u"errors={}".format(len(result.get("errors", []))),
            u"dry_run={}".format(1 if result.get("dry_run") else 0),
        ]
        for uid, message in result.get("errors", []):
            lines.append(u"error:{}:{}".format(uid, message))
        return u"\n".join(lines)
