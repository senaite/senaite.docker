# -*- coding: utf-8 -*-
from decimal import Decimal

from Products.Five.browser import BrowserView
from bika.lims import api
from bika.lims import senaiteMessageFactory as _
from senaite.core.api import dtime
from senaite.core.catalog import SETUP_CATALOG

from maitux.stock.stockbatchexpiry import expire_batch
from maitux.stock.stockbatchexpiry import get_operation_block_message
from maitux.stock.stockbatchexpiry import is_due_for_expiry


class StockBatchSplitView(BrowserView):
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
        uids = list(filter(api.is_uid, uids))
        return uids

    def get_source(self):
        uids = self.get_uids()
        if not uids:
            return None
        obj = api.get_object_by_uid(uids[0], default=None)
        if not api.is_object(obj):
            return None
        if api.get_portal_type(obj) != "StockBatch":
            return None
        return obj

    def _first_uid(self, value):
        if not value:
            return ""
        if isinstance(value, (list, tuple)):
            value = value[0] if value else ""
        value = api.safe_unicode(value)
        parts = value.splitlines()
        return parts[0].strip() if parts else ""

    def get_source_info(self):
        src = self.get_source()
        if not api.is_object(src):
            return {}
        stock_uid = self._first_uid(getattr(src, "stock", "") or "")
        stock = api.get_object_by_uid(stock_uid, default=None) if stock_uid else None
        unit_uid = self._first_uid(getattr(src, "unit", "") or "")
        unit = api.get_object_by_uid(unit_uid, default=None) if unit_uid else None
        return {
            "uid": api.get_uid(src),
            "batch_id": getattr(src, "batch_id", "") or api.get_title(src),
            "stock_uid": stock_uid,
            "stock_title": api.get_title(stock) if stock else "",
            "current_amount": getattr(src, "current_amount", "") or "",
            "unit_title": api.get_title(unit) if unit else "",
            "status": api.get_review_status(src) or "",
        }

    def get_target_candidates(self):
        src = self.get_source()
        if not api.is_object(src):
            return []
        src_uid = api.get_uid(src)
        src_stock = self._first_uid(getattr(src, "stock", "") or "")
        catalog = api.get_tool("portal_catalog")
        brains = catalog(
            portal_type="StockBatch",
            path={"query": api.get_path(self.context), "depth": 1},
        )
        items = []
        for brain in brains:
            batch = api.get_object(brain)
            if not api.is_object(batch):
                continue
            if api.get_uid(batch) == src_uid:
                continue
            if get_operation_block_message(batch):
                continue
            b_stock = self._first_uid(getattr(batch, "stock", "") or "")
            if src_stock and b_stock != src_stock:
                continue
            items.append({
                "uid": api.get_uid(batch),
                "title": getattr(batch, "batch_id", "") or api.get_title(batch),
                "current_amount": getattr(batch, "current_amount", "") or "",
            })
        items.sort(key=lambda i: api.safe_unicode(i.get("title", "")))
        return items

    def get_locations(self):
        catalog = api.get_tool(SETUP_CATALOG)
        brains = catalog(
            portal_type="InstrumentLocation",
            is_active=True,
            sort_on="sortable_title",
            sort_order="ascending",
        )
        items = []
        for b in brains:
            uid = getattr(b, "UID", None)
            if not uid:
                continue
            items.append({
                "uid": uid,
                "title": api.get_title(b) or uid,
            })
        return items

    def handle_submit(self):
        src = self.get_source()
        if not api.is_object(src):
            self.context.plone_utils.addPortalMessage(_("No items selected."), "warning")
            return self.request.response.redirect(api.get_url(self.context))

        now = dtime.now()
        workflow = api.get_tool("portal_workflow")
        if is_due_for_expiry(src, now=now):
            try:
                expire_batch(
                    src,
                    workflow_tool=workflow,
                    now=now,
                    operator=u"system",
                    remarks=u"Auto expired before split",
                )
            except Exception as exc:
                self.request["split_errors"] = [(api.get_uid(src), u"Failed to expire batch: {}".format(api.safe_unicode(exc)))]
                return self.index()

        if get_operation_block_message(src, now=now):
            self.context.plone_utils.addPortalMessage(_("No changes made."), "warning")
            return self.request.response.redirect(api.get_url(self.context))

        if not api.security.check_permission("Modify portal content", src):
            self.context.plone_utils.addPortalMessage(
                _("No changes made (no permission to modify selected batches)."),
                "warning",
            )
            return self.request.response.redirect(api.get_url(self.context))

        mode = api.safe_unicode(self.request.form.get("mode", "to_batch"))
        qty_raw = api.safe_unicode(self.request.form.get("quantity", "")).strip()
        remarks = api.safe_unicode(self.request.form.get("remarks", "") or u"").strip()

        try:
            qty = Decimal(qty_raw)
        except Exception:
            self.request["split_errors"] = [(api.get_uid(src), u"Invalid quantity")]
            return self.index()

        if qty <= 0:
            self.request["split_errors"] = [(api.get_uid(src), u"Quantity must be greater than 0")]
            return self.index()

        current = getattr(src, "current_amount", None)
        try:
            current = Decimal(current) if current is not None else Decimal("0.00")
        except Exception:
            current = Decimal("0.00")

        if qty > current:
            self.request["split_errors"] = [(api.get_uid(src), u"Quantity exceeds current amount")]
            return self.index()

        user = api.get_current_user()
        user_id = user.getId() if user else ""
        src_batch_id = getattr(src, "batch_id", "") or api.get_title(src)

        if mode == "to_batch":
            target_uid = api.safe_unicode(self.request.form.get("target_batch_uid", "")).strip()
            target = api.get_object_by_uid(target_uid, default=None) if api.is_uid(target_uid) else None
            if not api.is_object(target) or api.get_portal_type(target) != "StockBatch":
                self.request["split_errors"] = [(api.get_uid(src), u"Target batch is required")]
                return self.index()
            if is_due_for_expiry(target, now=now):
                try:
                    expire_batch(
                        target,
                        workflow_tool=workflow,
                        now=now,
                        operator=u"system",
                        remarks=u"Auto expired before split",
                    )
                except Exception as exc:
                    self.request["split_errors"] = [(api.get_uid(src), u"Failed to expire target batch: {}".format(api.safe_unicode(exc)))]
                    return self.index()
            block_message = get_operation_block_message(target, now=now)
            if block_message:
                self.request["split_errors"] = [(api.get_uid(src), block_message)]
                return self.index()
            if not api.security.check_permission("Modify portal content", target):
                self.request["split_errors"] = [(api.get_uid(src), u"No permission to modify target batch")]
                return self.index()

            src_stock = self._first_uid(getattr(src, "stock", "") or "")
            tgt_stock = self._first_uid(getattr(target, "stock", "") or "")
            if src_stock and tgt_stock and src_stock != tgt_stock:
                self.request["split_errors"] = [(api.get_uid(src), u"Stock must match")]
                return self.index()

            tgt_current = getattr(target, "current_amount", None)
            try:
                tgt_current = Decimal(tgt_current) if tgt_current is not None else Decimal("0.00")
            except Exception:
                tgt_current = Decimal("0.00")

            src.current_amount = current - qty
            target.current_amount = tgt_current + qty

            src_records = list(getattr(src, "usage_records", []) or [])
            src_records.append({
                "operation_type": u"split",
                "operator": api.safe_unicode(user_id),
                "operation_date": now,
                "quantity": qty,
                "remarks": remarks,
                "from_batch": u"",
            })
            src.usage_records = src_records

            tgt_records = list(getattr(target, "usage_records", []) or [])
            tgt_records.append({
                "operation_type": u"split",
                "operator": api.safe_unicode(user_id),
                "operation_date": now,
                "quantity": qty,
                "remarks": remarks,
                "from_batch": api.safe_unicode(src_batch_id),
            })
            target.usage_records = tgt_records

            try:
                src.reindexObject()
            except Exception:
                pass
            try:
                target.reindexObject()
            except Exception:
                pass

            self.context.plone_utils.addPortalMessage(_("Changes saved."), "info")
            return self.request.response.redirect(api.get_url(self.context))

        if mode == "new_batch":
            location_uid = api.safe_unicode(self.request.form.get("location_uid", "")).strip()
            if location_uid and not api.is_uid(location_uid):
                location_uid = ""

            new_batch = api.create(
                self.context,
                "StockBatch",
                stock=getattr(src, "stock", None),
                supplier=getattr(src, "supplier", None),
                batch=getattr(src, "batch", None),
                unit=getattr(src, "unit", None),
                expiry_date=getattr(src, "expiry_date", None),
                location=location_uid,
                current_amount=qty,
                usage_records=[{
                    "operation_type": u"split",
                    "operator": api.safe_unicode(user_id),
                    "operation_date": now,
                    "quantity": qty,
                    "remarks": remarks,
                    "from_batch": api.safe_unicode(src_batch_id),
                }],
            )
            try:
                new_batch.target_quantity = qty
            except Exception:
                pass
            # 如果新分装出来的批次已经超过有效期，创建后立即同步为过期状态。
            try:
                expire_batch(
                    new_batch,
                    workflow_tool=workflow,
                    now=now,
                    operator=u"system",
                    remarks=u"Auto expired on new split batch",
                )
            except Exception:
                pass

            # 补全 batch_id 和 title（subscriber 在 api.create 中拿不到 stock 字段无法生成）
            if not getattr(new_batch, "batch_id", None):
                stock_number = ""
                try:
                    s_uid = self._first_uid(getattr(new_batch, "stock", "") or "")
                    s_obj = api.get_object_by_uid(s_uid, default=None) if s_uid else None
                    stock_number = getattr(s_obj, "number", None) if s_obj else ""
                    stock_number = api.safe_unicode(stock_number) if stock_number else u""
                except Exception:
                    pass
                if stock_number:
                    from maitux.stock.subscribers import _get_next_batch_index
                    idx = _get_next_batch_index(stock_number)
                    new_batch.batch_id = u"{}/{}".format(stock_number, idx)
                    try:
                        new_batch.title = new_batch.batch_id
                    except Exception:
                        pass

            src.current_amount = current - qty
            src_records = list(getattr(src, "usage_records", []) or [])
            src_records.append({
                "operation_type": u"split",
                "operator": api.safe_unicode(user_id),
                "operation_date": now,
                "quantity": qty,
                "remarks": remarks,
                "from_batch": u"",
            })
            src.usage_records = src_records

            try:
                # 直接调用 catalog_object 强制写入 catalog（reindexObject 不生效）
                catalog = api.get_tool("portal_catalog")
                catalog.catalog_object(new_batch, api.get_path(new_batch))
            except Exception:
                pass
            try:
                src.reindexObject()
            except Exception:
                pass

            self.context.plone_utils.addPortalMessage(_("Changes saved."), "info")
            return self.request.response.redirect(api.get_url(self.context))

        self.request["split_errors"] = [(api.get_uid(src), u"Invalid mode")]
        return self.index()
