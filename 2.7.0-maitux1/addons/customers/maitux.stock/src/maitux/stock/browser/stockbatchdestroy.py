# -*- coding: utf-8 -*-
from decimal import Decimal

from Products.Five.browser import BrowserView
from bika.lims import api
from bika.lims import senaiteMessageFactory as _
from senaite.core.api import dtime
from Products.CMFCore.WorkflowCore import WorkflowException

from maitux.stock.stockbatchexpiry import expire_batch
from maitux.stock.stockbatchexpiry import is_due_for_expiry


class StockBatchDestroyView(BrowserView):
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
        return {
            "uid": api.get_uid(batch),
            "title": api.get_title(batch),
            "batch_id": getattr(batch, "batch_id", "") or "",
            "current_amount": getattr(batch, "current_amount", "") or "",
            "unit_title": api.get_title(unit) if unit else "",
        }

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
        user = api.get_current_user()
        user_id = user.getId() if user else ""

        updated = 0
        skipped_permission = 0
        workflow = api.get_tool("portal_workflow")
        for batch in batches:
            # 销毁前先补齐过期状态，保证历史轨迹完整。
            if is_due_for_expiry(batch, now=now):
                try:
                    expire_batch(
                        batch,
                        workflow_tool=workflow,
                        now=now,
                        operator=u"system",
                        remarks=u"Auto expired before destroy",
                    )
                except Exception:
                    pass
            if api.get_review_status(batch) == "destroyed":
                continue
            if not workflow:
                skipped_permission += 1
                continue
            if not api.security.check_permission("Modify portal content", batch):
                skipped_permission += 1
                continue

            # 记录销毁前的数量，用于流水记录
            current = getattr(batch, "current_amount", None)
            try:
                current = Decimal(current) if current is not None else Decimal("0.00")
            except Exception:
                current = Decimal("0.00")

            remarks = self.get_posted_remarks(api.get_uid(batch))

            # 先执行工作流迁移，成功后再清零数量（避免迁移失败导致数量归零但状态未变）
            try:
                workflow.doActionFor(batch, "destroy")
            except WorkflowException:
                skipped_permission += 1
                continue
            except Exception:
                skipped_permission += 1
                continue

            try:
                batch.current_amount = Decimal("0.00")
            except Exception:
                batch.current_amount = 0

            records = getattr(batch, "usage_records", None) or []
            if not isinstance(records, (list, tuple)):
                records = []
            records = list(records)
            records.append({
                "operation_type": u"destroy",
                "operator": api.safe_unicode(user_id),
                "operation_date": now,
                "quantity": current,
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
