# -*- coding: utf-8 -*-
import collections

from bika.lims import api
from bika.lims.utils import get_link
from senaite.app.listing import ListingView
from senaite.core.api import dtime
from senaite.core.i18n import translate
from decimal import Decimal

from maitux.stock import _
from maitux.stock.browser.stockbatchactions import ACTION_CONSUME
from maitux.stock.browser.stockbatchactions import ACTION_DESTROY
from maitux.stock.browser.stockbatchactions import ACTION_PRINT
from maitux.stock.browser.stockbatchactions import ACTION_RETURN
from maitux.stock.browser.stockbatchactions import ACTION_SPLIT
from maitux.stock.browser.stockbatchactions import ACTION_STOCKTAKE
from maitux.stock.browser.stockbatchactions import get_allowed_action_ids_for_batches
from maitux.stock.browser.stockbatchactions import get_transition_items_for_action_ids
from maitux.stock.browser.stockbatchactions import get_transition_items_for_batch
from maitux.stock.stockbatchexpiry import REVIEW_STATE_EXPIRED
from maitux.stock.stockbatchexpiry import is_due_for_expiry


def is_batch_visible_in_tab(batch, review_state_id, now=None):
    """判断批次在当前页签下是否应该显示。"""
    # 中文注释：Active 页签除了看工作流状态外，还要额外隐藏“已到期但尚未同步为 expired”的批次。
    if review_state_id == "default" and is_due_for_expiry(batch, now=now):
        return False
    return True


def should_show_select_for_batch(review_state_id, status):
    """判断当前批次在页签中是否显示复选框。"""
    # 中文注释：All 页签只负责汇总展示，是否允许执行具体操作交给后端动作校验，
    # 前端不再对某些状态单独隐藏复选框，避免同页签下出现“有的能选、有的不能选”的不一致表现。
    return True


class StockBatchesView(ListingView):
    def __init__(self, context, request):
        super(StockBatchesView, self).__init__(context, request)

        self.title = translate(_(
            u"listing_stockbatches_title",
            default=u"Stock Batches"
        ))
        self.catalog = "portal_catalog"
        self.show_search = True
        self.contentFilter = {
            "portal_type": "StockBatch",
            "sort_on": "created",
            "sort_order": "descending",
            "path": {
                "query": api.get_path(self.context),
                "depth": 1,
            },
        }
        self.context_actions = {
            _(u"listing_stockbatches_action_add", default=u"Add"): {
                "url": "++add++StockBatch",
                "permission": "cmf.AddPortalContent",
                "icon": "senaite_theme/icon/plus",
            }
        }
        self.show_select_column = True

        self.columns = collections.OrderedDict((
            ("batch_id", {"title": _(u"listing_stockbatches_column_batch_id", default=u"Batch ID"), "toggle": True}),
            ("stock", {"title": _(u"listing_stockbatches_column_stock", default=u"Stock"), "toggle": True}),
            ("supplier", {"title": _(u"listing_stockbatches_column_supplier", default=u"Supplier"), "toggle": True}),
            ("current_amount", {"title": _(u"listing_stockbatches_column_current_amount", default=u"Current Amount"), "toggle": True}),
            ("target_quantity", {"title": _(u"listing_stockbatches_column_target_quantity", default=u"Target Quantity"), "toggle": True}),
            ("unit", {"title": _(u"listing_stockbatches_column_unit", default=u"Unit"), "toggle": True}),
            ("expiry_date", {"title": _(u"listing_stockbatches_column_expiry_date", default=u"Expiry Date"), "toggle": True}),
            ("created_by", {"title": _(u"listing_stockbatches_column_created_by", default=u"Created By"), "toggle": True, "index": "Creator"}),
            ("created_date", {"title": _(u"listing_stockbatches_column_created_date", default=u"Created Date"), "toggle": True, "index": "created"}),
            ("status", {"title": _(u"listing_stockbatches_column_status", default=u"Status"), "toggle": True}),
        ))

        self.review_states = [
            {
                "id": "default",
                "title": _(u"listing_state_active", default=u"Active"),
                "contentFilter": {"review_state": "active"},
                "transitions": get_transition_items_for_action_ids([
                    ACTION_CONSUME,
                    ACTION_SPLIT,
                    ACTION_RETURN,
                    ACTION_STOCKTAKE,
                    ACTION_DESTROY,
                    ACTION_PRINT,
                ]),
                "columns": list(self.columns.keys()),
            }, {
                "id": "expired",
                "title": _(u"listing_state_expired", default=u"Expired"),
                "contentFilter": {"review_state": REVIEW_STATE_EXPIRED},
                "transitions": get_transition_items_for_action_ids([
                    ACTION_DESTROY,
                    ACTION_PRINT,
                ]),
                "columns": list(self.columns.keys()),
            }, {
                "id": "destroyed",
                "title": _(u"listing_state_destroyed", default=u"Destroyed"),
                "contentFilter": {"review_state": "destroyed"},
                "transitions": get_transition_items_for_action_ids([
                    ACTION_PRINT,
                ]),
                "columns": list(self.columns.keys()),
            }, {
                "id": "all",
                "title": _(u"listing_state_all", default=u"All"),
                "contentFilter": {},
                "transitions": [],
                "columns": list(self.columns.keys()),
            }
        ]

    def get_allowed_transitions_for(self, uids):
        """返回当前勾选批次可显示的批量动作按钮。"""
        if not uids:
            return []

        batches = []
        for uid in uids:
            batch = api.get_object_by_uid(uid, default=None)
            if batch is None:
                continue
            batches.append(batch)
        if not batches:
            return []

        action_ids = get_allowed_action_ids_for_batches(batches)

        # 中文注释：新版 listing 会按当前页签的 transitions 继续做一次白名单过滤，
        # 这里提前对齐该规则，确保各页签按钮与 All 页签的动态交集结果一致。
        allowed_ids = [
            item.get("id") for item in self.review_state.get("transitions", [])
            if item.get("id")
        ]
        if allowed_ids:
            action_ids = [action_id for action_id in action_ids if action_id in allowed_ids]

        return get_transition_items_for_action_ids(action_ids)

    def get_catalog_query(self, **kw):
        query = super(StockBatchesView, self).get_catalog_query(**kw)
        searchterm = kw.get("searchterm", "") or self.request.get("searchterm", "") or ""
        searchterm = api.safe_unicode(searchterm).strip()
        if searchterm:
            query["Title"] = searchterm
        return query

    def folderitems(self):
        items = super(StockBatchesView, self).folderitems()
        review_state_id = self.review_state.get("id", "")
        if review_state_id != "default":
            return items

        visible_items = []
        for item in items:
            batch = item.get("obj")
            if batch is None:
                visible_items.append(item)
                continue
            batch = api.get_object(batch)
            if not is_batch_visible_in_tab(batch, review_state_id):
                continue
            visible_items.append(item)
        return visible_items

    def _first_uid(self, value):
        if not value:
            return ""
        if isinstance(value, (list, tuple)):
            value = value[0] if value else ""
        value = api.safe_unicode(value)
        parts = value.splitlines()
        return parts[0] if parts else ""

    def _format_dt(self, value):
        if not value:
            return ""
        try:
            ansi = dtime.to_ansi(value, show_time=True)
            if not ansi:
                return ""
            return "{}-{}-{} {}:{}:{}".format(
                ansi[0:4], ansi[4:6], ansi[6:8],
                ansi[8:10], ansi[10:12], ansi[12:14],
            )
        except Exception:
            return ""

    def _format_amount(self, value):
        try:
            val = Decimal(value)
            # Ensure "0.00" is shown, not empty
            return "{:.2f}".format(val)
        except Exception:
            return "{}".format(value if value is not None else "0")

    def folderitem(self, obj, item, index):
        item = super(StockBatchesView, self).folderitem(obj, item, index)
        obj = api.get_object(obj)
        current_state_id = self.review_state.get("id", "")

        batch_id = getattr(obj, "batch_id", "") or ""
        item["batch_id"] = batch_id

        stock_uid = self._first_uid(getattr(obj, "stock", "") or "")
        stock = api.get_object_by_uid(stock_uid, default=None) if stock_uid else None
        item["stock"] = api.get_title(stock) if stock else ""

        supplier_uid = self._first_uid(getattr(obj, "supplier", "") or "")
        supplier = api.get_object_by_uid(supplier_uid, default=None) if supplier_uid else None
        item["supplier"] = api.get_title(supplier) if supplier else ""

        item["current_amount"] = self._format_amount(getattr(obj, "current_amount", None))
        item["target_quantity"] = self._format_amount(getattr(obj, "target_quantity", None))

        unit_uid = self._first_uid(getattr(obj, "unit", "") or "")
        unit = api.get_object_by_uid(unit_uid, default=None) if unit_uid else None
        item["unit"] = api.get_title(unit) if unit else ""

        expiry = getattr(obj, "expiry_date", None)
        item["expiry_date"] = self._format_dt(expiry) if expiry else ""

        item["status"] = api.get_review_status(obj) or ""
        item["transitions"] = get_transition_items_for_batch(obj)
        if not should_show_select_for_batch(current_state_id, item["status"]):
            item["disabled"] = True
            item["show_select"] = False

        created_by = getattr(obj, "created_by", "") or ""
        if not created_by:
            try:
                created_by = obj.Creator()
            except Exception:
                created_by = ""
        item["created_by"] = created_by

        created_dt = getattr(obj, "created_date", None)
        if not created_dt:
            try:
                created_dt = obj.created()
            except Exception:
                created_dt = None
        item["created_date"] = self._format_dt(created_dt) if created_dt else ""

        item["replace"]["batch_id"] = get_link(
            href=api.get_url(obj),
            value=batch_id or api.get_title(obj),
            csrf=False,
        )

        return item
