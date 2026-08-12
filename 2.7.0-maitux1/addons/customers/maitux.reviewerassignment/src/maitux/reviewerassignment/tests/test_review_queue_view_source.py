# -*- coding: utf-8 -*-
"""审核队列视图源码回归测试"""

import os
import unittest


VIEW_SOURCE = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, "browser", "review_queue.py"))


class TestReviewQueueViewSource(unittest.TestCase):
    """避免再次调用依赖 mine 状态的父类 before_render"""

    def test_review_queue_uses_listingview_before_render(self):
        """审核队列要跳过 WorksheetsView.before_render 的 mine 逻辑"""
        with open(VIEW_SOURCE, "r") as handle:
            source = handle.read()

        self.assertIn("ListingView.before_render(self)", source)
        self.assertNotIn("super(ReviewerQueueView, self).before_render()", source)

    def test_review_queue_sets_default_review_state(self):
        """审核队列必须显式把默认状态指向待审核"""
        with open(VIEW_SOURCE, "r") as handle:
            source = handle.read()

        self.assertIn('default_review_state = "to_be_verified"', source)
