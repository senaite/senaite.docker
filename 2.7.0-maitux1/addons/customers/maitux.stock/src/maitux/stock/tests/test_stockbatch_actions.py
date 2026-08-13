# -*- coding: utf-8 -*-
import importlib.util
import os
import sys
import types
import unittest


def load_stockbatchactions_module():
    """加载 stockbatchactions 模块，并替换外部依赖。"""
    api_module = types.SimpleNamespace(
        safe_unicode=lambda value: u"" if value is None else u"{}".format(value),
        is_object=lambda obj: bool(obj) and getattr(obj, "is_object", True),
        is_uid=lambda value: bool(value),
        get_object_by_uid=lambda uid, default=None: default,
        get_portal_type=lambda obj: getattr(obj, "portal_type", u""),
    )

    sys.modules["Products"] = types.ModuleType("Products")
    sys.modules["Products.Five"] = types.ModuleType("Products.Five")
    browser_module = types.ModuleType("Products.Five.browser")
    browser_module.BrowserView = object
    sys.modules["Products.Five.browser"] = browser_module

    sys.modules["bika"] = types.ModuleType("bika")
    sys.modules["bika.lims"] = types.ModuleType("bika.lims")
    sys.modules["bika.lims"].api = api_module
    sys.modules["bika.lims.api"] = api_module

    expiry_module = types.ModuleType("maitux.stock.stockbatchexpiry")
    expiry_module.REVIEW_STATE_DESTROYED = u"destroyed"
    expiry_module.REVIEW_STATE_EXPIRED = u"expired"
    expiry_module.get_review_state = lambda batch: getattr(batch, "review_state", u"")
    expiry_module.is_due_for_expiry = (
        lambda batch, now=None: bool(getattr(batch, "is_due_for_expiry", False))
    )
    sys.modules["maitux"] = types.ModuleType("maitux")
    sys.modules["maitux.stock"] = types.ModuleType("maitux.stock")
    sys.modules["maitux.stock.stockbatchexpiry"] = expiry_module

    file_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "browser", "stockbatchactions.py"))
    spec = importlib.util.spec_from_file_location("test_stockbatchactions_module", file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DummyBatch(object):
    """用于验证批量动作规则的最小批次对象。"""

    def __init__(self, review_state=u"active", is_due_for_expiry=False):
        self.review_state = review_state
        self.is_due_for_expiry = is_due_for_expiry
        self.portal_type = "StockBatch"
        self.is_object = True


class TestStockBatchActions(unittest.TestCase):

    def setUp(self):
        self.actions = load_stockbatchactions_module()

    def test_due_batch_is_treated_as_expired(self):
        """已到期但未同步工作流的批次要按过期处理。"""
        batch = DummyBatch(review_state=u"active", is_due_for_expiry=True)

        status = self.actions.get_effective_batch_status(batch)

        self.assertEqual(status, u"expired")

    def test_mixed_active_and_expired_only_keep_expired_actions(self):
        """active 和 expired 混选时只保留两者交集动作。"""
        allowed = self.actions.get_allowed_action_ids_for_statuses(
            [u"active", u"expired"],
            selection_count=2,
        )

        self.assertEqual(allowed, [
            self.actions.ACTION_DESTROY,
            self.actions.ACTION_PRINT,
        ])

    def test_mixed_active_and_destroyed_only_keep_destroyed_actions(self):
        """active 和 destroyed 混选时只保留 destroyed 能用的动作。"""
        allowed = self.actions.get_allowed_action_ids_for_statuses(
            [u"active", u"destroyed"],
            selection_count=2,
        )

        self.assertEqual(allowed, [self.actions.ACTION_PRINT])

    def test_split_requires_single_selection(self):
        """分装只允许单选批次。"""
        allowed = self.actions.get_allowed_action_ids_for_statuses(
            [u"active", u"active"],
            selection_count=2,
        )

        self.assertNotIn(self.actions.ACTION_SPLIT, allowed)

    def test_single_active_selection_keeps_split(self):
        """单选 active 批次时仍允许分装。"""
        allowed = self.actions.get_allowed_action_ids_for_statuses(
            [u"active"],
            selection_count=1,
        )

        self.assertIn(self.actions.ACTION_SPLIT, allowed)

    def test_transition_items_keep_titles_and_order(self):
        """标准 listing 需要每个动作同时提供 id 和 title。"""
        transitions = self.actions.get_transition_items_for_action_ids([
            self.actions.ACTION_DESTROY,
            self.actions.ACTION_PRINT,
        ])

        self.assertEqual(transitions, [
            {
                "id": self.actions.ACTION_DESTROY,
                "title": u"Destroy",
                "css_class": u"btn btn-danger",
            },
            {
                "id": self.actions.ACTION_PRINT,
                "title": u"Print Labels",
                "css_class": u"btn btn-outline-secondary",
            },
        ])

    def test_transition_items_keep_button_colors(self):
        """各个自定义动作应保留原有按钮颜色。"""
        transitions = self.actions.get_transition_items_for_action_ids([
            self.actions.ACTION_CONSUME,
            self.actions.ACTION_SPLIT,
            self.actions.ACTION_RETURN,
            self.actions.ACTION_STOCKTAKE,
        ])

        self.assertEqual(transitions, [
            {
                "id": self.actions.ACTION_CONSUME,
                "title": u"Consume",
                "css_class": u"btn btn-success",
            },
            {
                "id": self.actions.ACTION_SPLIT,
                "title": u"Split",
                "css_class": u"btn btn-primary",
            },
            {
                "id": self.actions.ACTION_RETURN,
                "title": u"Return",
                "css_class": u"btn btn-warning",
            },
            {
                "id": self.actions.ACTION_STOCKTAKE,
                "title": u"Stocktake",
                "css_class": u"btn btn-primary",
            },
        ])
