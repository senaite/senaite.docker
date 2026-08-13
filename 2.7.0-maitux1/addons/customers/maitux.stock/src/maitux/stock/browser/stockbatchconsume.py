# -*- coding: utf-8 -*-
from decimal import Decimal

import transaction
from Products.Five.browser import BrowserView
from ZODB.POSException import ConflictError
from bika.lims import api
from bika.lims import senaiteMessageFactory as _
from senaite.core.api import dtime
from senaite.core import logger

from maitux.stock.stockbatchexpiry import expire_batch
from maitux.stock.stockbatchexpiry import get_operation_block_message
from maitux.stock.stockbatchexpiry import is_due_for_expiry


class StockBatchConsumeView(BrowserView):
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

    def _first_uid(self, value):
        if not value:
            return ""
        if isinstance(value, (list, tuple)):
            value = value[0] if value else ""
        value = api.safe_unicode(value)
        parts = value.splitlines()
        return parts[0].strip() if parts else ""

    def get_display_info(self, batch):
        stock_uid = self._first_uid(getattr(batch, "stock", "") or "")
        stock = api.get_object_by_uid(stock_uid, default=None) if stock_uid else None

        unit_uid = self._first_uid(getattr(batch, "unit", "") or "")
        unit = api.get_object_by_uid(unit_uid, default=None) if unit_uid else None

        return {
            "uid": api.get_uid(batch),
            "title": api.get_title(batch),
            "batch_id": getattr(batch, "batch_id", "") or "",
            "stock_title": api.get_title(stock) if stock else "",
            "current_amount": getattr(batch, "current_amount", "") or "",
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
            # 业务双保险：即使定时任务尚未来得及执行，到期批次也必须先转为过期。
            if is_due_for_expiry(batch, now=now):
                try:
                    expire_batch(
                        batch,
                        workflow_tool=workflow,
                        now=now,
                        operator=u"system",
                        remarks=u"Auto expired before consume",
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
            if qty <= 0:
                errors.append((uid, u"Quantity must be greater than 0"))
                continue

            current = getattr(batch, "current_amount", None)
            try:
                current = Decimal(current) if current is not None else Decimal("0.00")
            except Exception:
                current = Decimal("0.00")

            if qty > current:
                errors.append((uid, u"Quantity exceeds current amount"))
                continue

            remarks = self.get_posted_remarks(uid)
            updates.append((batch, qty, remarks, current))

        if errors:
            self.request["consume_errors"] = errors
            return self.index()

        user = api.get_current_user()
        user_id = user.getId() if user else ""
        # 批量扣减必须保持原子性，任一批次失败时回滚本次请求中的全部改动。
        savepoint = transaction.savepoint()

        updated = 0
        try:
            for batch, qty, remarks, current in updates:
                if not api.security.check_permission("Modify portal content", batch):
                    raise UnauthorizedConsumeError(
                        u"No permission to modify batch '{}'".format(api.get_uid(batch))
                    )

                new_amount = current - qty
                batch.current_amount = new_amount

                records = getattr(batch, "usage_records", None) or []
                if not isinstance(records, (list, tuple)):
                    records = []
                records = list(records)
                records.append({
                    "operation_type": u"consume",
                    "operator": api.safe_unicode(user_id),
                    "operation_date": now,
                    "quantity": qty,
                    "remarks": remarks,
                })
                batch.usage_records = records
                batch.reindexObject()
                updated += 1
        except ConflictError:
            savepoint.rollback()
            logger.exception("Stock batch consume conflict, rolled back all updates")
            raise
        except Exception as exc:
            savepoint.rollback()
            logger.exception("Stock batch consume failed, rolled back all updates: %s", exc)
            self.context.plone_utils.addPortalMessage(
                _("Consume failed. All changes have been rolled back."),
                "error",
            )
            self.request["consume_errors"] = [(u"*", api.safe_unicode(exc))]
            return self.index()

        if updated == 0:
            self.context.plone_utils.addPortalMessage(_("No changes made."), "warning")
            return self.request.response.redirect(api.get_url(self.context))

        self.context.plone_utils.addPortalMessage(_("Changes saved."), "info")
        return self.request.response.redirect(api.get_url(self.context))


class UnauthorizedConsumeError(Exception):
    """批量扣减时的权限异常。"""
