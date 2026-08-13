# -*- coding: utf-8 -*-
import importlib.util
import os
import sys
import types
import unittest


def load_stockbatches_module():
    """加载 stockbatches 模块，并用最小桩替换外部依赖。"""
    uid_map = {}
    api_module = types.SimpleNamespace(
        safe_unicode=lambda value: u"" if value is None else u"{}".format(value),
        get_path=lambda context: "/stub",
        get_url=lambda context: "/stub",
        get_title=lambda obj: getattr(obj, "title", u"") if obj else u"",
        get_object=lambda obj: obj,
        get_object_by_uid=lambda uid, default=None: uid_map.get(uid, default),
        get_review_status=lambda obj: getattr(obj, "review_state", u""),
    )

    sys.modules["bika"] = types.ModuleType("bika")
    sys.modules["bika.lims"] = types.ModuleType("bika.lims")
    sys.modules["bika.lims"].api = api_module
    sys.modules["bika.lims.api"] = api_module

    utils_module = types.ModuleType("bika.lims.utils")
    utils_module.get_link = lambda href, value, csrf=False: value
    sys.modules["bika.lims.utils"] = utils_module

    listing_module = types.ModuleType("senaite.app.listing")
    class FakeListingView(object):
        def __init__(self, context, request):
            self.context = context
            self.request = request
            self.review_state = {}
            self.columns = {}
        def get_catalog_query(self, **kw):
            return {}
        def folderitems(self):
            return []
        def folderitem(self, obj, item, index):
            return item
    listing_module.ListingView = FakeListingView
    sys.modules["senaite"] = types.ModuleType("senaite")
    sys.modules["senaite.app"] = types.ModuleType("senaite.app")
    sys.modules["senaite.app.listing"] = listing_module

    dtime_module = types.ModuleType("senaite.core.api")
    dtime_module.dtime = types.SimpleNamespace(to_ansi=lambda value, show_time=True: value)
    sys.modules["senaite.core"] = types.ModuleType("senaite.core")
    sys.modules["senaite.core.api"] = dtime_module

    expiry_module = types.ModuleType("maitux.stock.stockbatchexpiry")
    expiry_module.REVIEW_STATE_EXPIRED = u"expired"
    expiry_module.is_due_for_expiry = (
        lambda batch, now=None: bool(getattr(batch, "is_due_for_expiry", False))
    )
    actions_module = types.ModuleType("maitux.stock.browser.stockbatchactions")
    actions_module.ACTION_CONSUME = "stockbatch_consume"
    actions_module.ACTION_SPLIT = "stockbatch_split"
    actions_module.ACTION_RETURN = "stockbatch_return"
    actions_module.ACTION_DESTROY = "stockbatch_destroy"
    actions_module.ACTION_STOCKTAKE = "stockbatch_stocktake"
    actions_module.ACTION_PRINT = "stockbatch_print"
    actions_module.get_transition_items_for_action_ids = (
        lambda action_ids: [{"id": action_id, "title": action_id} for action_id in action_ids]
    )
    actions_module.get_transition_items_for_batch = (
        lambda batch, now=None: [{"id": getattr(batch, "transition_id", u"stockbatch_print"),
                                  "title": getattr(batch, "transition_id", u"stockbatch_print")}]
    )
    actions_module.get_allowed_action_ids_for_batches = (
        lambda batches, now=None: list(getattr(batches[0], "allowed_action_ids", [])) if batches else []
    )
    sys.modules["maitux"] = types.ModuleType("maitux")
    sys.modules["maitux.stock"] = types.ModuleType("maitux.stock")
    sys.modules["maitux.stock.browser"] = types.ModuleType("maitux.stock.browser")
    sys.modules["maitux.stock.browser.stockbatchactions"] = actions_module
    sys.modules["maitux.stock.stockbatchexpiry"] = expiry_module

    file_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "browser", "stockbatches.py"))
    spec = importlib.util.spec_from_file_location("test_stockbatches_module", file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._test_uid_map = uid_map
    return module


class DummyBatch(object):
    """用于验证列表页签过滤逻辑的最小批次对象。"""

    def __init__(self, is_due_for_expiry=False, transition_id=u"stockbatch_print",
                 allowed_action_ids=None):
        self.is_due_for_expiry = is_due_for_expiry
        self.transition_id = transition_id
        self.allowed_action_ids = allowed_action_ids or []


class TestStockBatchesView(unittest.TestCase):

    def setUp(self):
        self.stockbatches = load_stockbatches_module()

    def test_active_tab_hides_due_batches(self):
        """Active 页签不应显示已经到期的批次。"""
        batch = DummyBatch(is_due_for_expiry=True)

        visible = self.stockbatches.is_batch_visible_in_tab(
            batch,
            review_state_id="default",
        )

        self.assertFalse(visible)

    def test_expired_tab_keeps_due_batches(self):
        """Expired 页签仍然需要显示已到期批次。"""
        batch = DummyBatch(is_due_for_expiry=True)

        visible = self.stockbatches.is_batch_visible_in_tab(
            batch,
            review_state_id="expired",
        )

        self.assertTrue(visible)

    def test_all_tab_keeps_checkbox_for_expired_rows(self):
        """All 页签中的过期批次也应保留复选框。"""
        show_select = self.stockbatches.should_show_select_for_batch(
            review_state_id="all",
            status=u"expired",
        )

        self.assertTrue(show_select)

    def test_default_tab_declares_standard_transitions(self):
        """Active 页签应直接使用标准 listing transitions 配置。"""
        view = self.stockbatches.StockBatchesView(object(), {})

        default_state = [rv for rv in view.review_states if rv["id"] == "default"][0]
        self.assertEqual(
            [item["id"] for item in default_state["transitions"]],
            [
                "stockbatch_consume",
                "stockbatch_split",
                "stockbatch_return",
                "stockbatch_stocktake",
                "stockbatch_destroy",
                "stockbatch_print",
            ],
        )

    def test_default_tab_selected_active_batch_returns_custom_actions(self):
        """Active 页签选择 active 批次时应返回自定义批量动作。"""
        batch = DummyBatch(allowed_action_ids=[
            "stockbatch_consume",
            "stockbatch_split",
            "stockbatch_return",
            "stockbatch_stocktake",
            "stockbatch_destroy",
            "stockbatch_print",
        ])
        self.stockbatches._test_uid_map["UID-1"] = batch
        view = self.stockbatches.StockBatchesView(object(), {})
        view.review_state = {"id": "default", "transitions": [
            {"id": "stockbatch_consume"},
            {"id": "stockbatch_split"},
            {"id": "stockbatch_return"},
            {"id": "stockbatch_stocktake"},
            {"id": "stockbatch_destroy"},
            {"id": "stockbatch_print"},
        ]}

        transitions = view.get_allowed_transitions_for(["UID-1"])

        self.assertEqual(
            [item["id"] for item in transitions],
            [
                "stockbatch_consume",
                "stockbatch_split",
                "stockbatch_return",
                "stockbatch_stocktake",
                "stockbatch_destroy",
                "stockbatch_print",
            ],
        )

    def test_all_tab_selected_active_batch_keeps_all_custom_actions(self):
        """All 页签选择 active 批次时不应退化成只剩 workflow destroy。"""
        batch = DummyBatch(allowed_action_ids=[
            "stockbatch_consume",
            "stockbatch_split",
            "stockbatch_return",
            "stockbatch_stocktake",
            "stockbatch_destroy",
            "stockbatch_print",
        ])
        self.stockbatches._test_uid_map["UID-2"] = batch
        view = self.stockbatches.StockBatchesView(object(), {})
        view.review_state = {"id": "all", "transitions": []}

        transitions = view.get_allowed_transitions_for(["UID-2"])

        self.assertEqual(
            [item["id"] for item in transitions],
            [
                "stockbatch_consume",
                "stockbatch_split",
                "stockbatch_return",
                "stockbatch_stocktake",
                "stockbatch_destroy",
                "stockbatch_print",
            ],
        )
