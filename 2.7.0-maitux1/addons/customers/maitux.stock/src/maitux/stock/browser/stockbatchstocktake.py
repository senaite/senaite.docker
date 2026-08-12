# -*- coding: utf-8 -*-
from decimal import Decimal

from Products.Five.browser import BrowserView
from bika.lims import api
from bika.lims import senaiteMessageFactory as _
from senaite.core.api import dtime

from maitux.stock.stockbatchexpiry import expire_batch
from maitux.stock.stockbatchexpiry import get_operation_block_message
from maitux.stock.stockbatchexpiry import is_due_for_expiry


class StockBatchStocktakeView(BrowserView):
    def __call__(self):
        if "form.button.cancel" in getattr(self.request, "form", {}):
            return self.request.response.redirect(api.get_url(self.context))
        if "form.button.submit" in getattr(self.request, "form", {}):
            return self.handle_submit()
        return self.index()

    def get_uids(self):
        uids = self.request.get("uids", "")
        if isinstance(uids, (list, tuple)):
            uids = ",".join(uids)
        uids = [u.strip() for u in api.safe_unicode(uids).split(",") if u.strip()]
        uids = filter(api.is_uid, uids)
        return list(uids)

    def get_batches(self):
        batches = []
        for uid in self.get_uids():
            obj = api.get_object_by_uid(uid, default=None)
            if not api.is_object(obj):
                continue
            if api.get_portal_type(obj) != "StockBatch":
                continue
            batches.append(obj)
        return batches

    def get_display_info(self, batch):
        unit_uid = getattr(batch, "unit", "") or ""
        if isinstance(unit_uid, (list, tuple)):
            unit_uid = unit_uid[0] if unit_uid else ""
        parts = api.safe_unicode(unit_uid).splitlines()
        unit_uid = parts[0].strip() if parts else ""
        unit = api.get_object_by_uid(unit_uid, default=None) if unit_uid else None

        cur = getattr(batch, "current_amount", None)
        try:
            cur = Decimal(cur) if cur is not None else Decimal("0.00")
        except Exception:
            cur = Decimal("0.00")

        return {
            "uid": api.get_uid(batch),
            "title": api.get_title(batch),
            "batch_id": getattr(batch, "batch_id", "") or "",
            "current_amount": cur,
            "unit_title": api.get_title(unit) if unit else "",
        }

    def get_posted_qty(self, uid):
        key = "qty.{}".format(uid)
        raw = self.request.form.get(key, "")
        raw = api.safe_unicode(raw).strip()
        if not raw:
            return None
        try:
            return Decimal(raw)
        except Exception:
            return None

    def get_posted_remarks(self, uid):
        key = "remarks.{}".format(uid)
        raw = self.request.form.get(key, "")
        return api.safe_unicode(raw or u"").strip()

    def handle_submit(self):
        batches = self.get_batches()
        if not batches:
            self.context.plone_utils.addPortalMessage(_("No items selected."), "warning")
            return self.request.response.redirect(api.get_url(self.context))

        now = dtime.now()
        workflow = api.get_tool("portal_workflow")
        errors = []
        updates = []
        for batch in batches:
            # 盘点前先同步过期状态，确保过期批次只能进入销毁流程。
            if is_due_for_expiry(batch, now=now):
                try:
                    expire_batch(
                        batch,
                        workflow_tool=workflow,
                        now=now,
                        operator=u"system",
                        remarks=u"Auto expired before stocktake",
                    )
                except Exception as exc:
                    errors.append((api.get_uid(batch), u"Failed to expire batch: {}".format(api.safe_unicode(exc))))
                    continue

            block_message = get_operation_block_message(batch, now=now)
            if block_message:
                errors.append((api.get_uid(batch), block_message))
                continue
            uid = api.get_uid(batch)
            qty = self.get_posted_qty(uid)
            if qty is None:
                errors.append((uid, u"Invalid quantity"))
                continue
            if qty < 0:
                errors.append((uid, u"Quantity cannot be negative"))
                continue

            remarks = self.get_posted_remarks(uid)
            updates.append((batch, qty, remarks))

        if errors:
            self.request["stocktake_errors"] = errors
            return self.index()

        user = api.get_current_user()
        user_id = user.getId() if user else ""

        updated = 0
        skipped_permission = 0
        for batch, qty, remarks in updates:
            if not api.security.check_permission("Modify portal content", batch):
                skipped_permission += 1
                continue
            
            try:
                batch.current_amount = qty
            except Exception:
                pass

            records = getattr(batch, "usage_records", None) or []
            if not isinstance(records, (list, tuple)):
                records = []
            records = list(records)
            records.append({
                "operation_type": u"stocktake",
                "operator": api.safe_unicode(user_id),
                "operation_date": now,
                "quantity": qty,
                "remarks": remarks,
            })
            batch.usage_records = records
            try:
                batch.reindexObject()
            except Exception:
                pass
            updated += 1

        if updated == 0 and skipped_permission > 0:
            self.context.plone_utils.addPortalMessage(
                _("No changes made (no permission to modify selected batches)."),
                "warning",
            )
            return self.request.response.redirect(api.get_url(self.context))

        if updated == 0:
            self.context.plone_utils.addPortalMessage(_("No changes made."), "warning")
            return self.request.response.redirect(api.get_url(self.context))

        self.context.plone_utils.addPortalMessage(_("Changes saved."), "info")
        return self.request.response.redirect(api.get_url(self.context))
