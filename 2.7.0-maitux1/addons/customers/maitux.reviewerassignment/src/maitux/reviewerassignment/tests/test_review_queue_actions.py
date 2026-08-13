# -*- coding: utf-8 -*-
"""审核队列批量动作测试"""

import imp
import os
import unittest


MODULE_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, "review_logic.py"))
review_logic = imp.load_source("review_logic", MODULE_PATH)


class DummyAnalysis(object):
    """模拟分析项对象"""

    def __init__(self, uid, review_state):
        self.uid = uid
        self.review_state = review_state


class DummyWorksheet(object):
    """模拟工作表对象"""

    def __init__(self, title, reviewer_userid, analyses):
        self.title = title
        self.reviewer_userid = reviewer_userid
        self._analyses = analyses

    def getAnalyses(self):
        return list(self._analyses)


class TestReviewQueueActions(unittest.TestCase):
    """校验批量审核前的数据筛选逻辑"""

    def test_collect_verifiable_analyses_filters_to_be_verified(self):
        """只有待复核分析项会进入审核队列"""
        worksheet = DummyWorksheet("WS-001", "reviewer01", [
            DummyAnalysis("A1", "to_be_verified"),
            DummyAnalysis("A2", "verified"),
        ])

        selected, errors = review_logic.collect_verifiable_analyses(
            [worksheet], "reviewer01")

        self.assertEqual(["A1"], [item.uid for item in selected])
        self.assertEqual([], errors)

    def test_collect_verifiable_analyses_rejects_other_reviewer(self):
        """当前用户不是被分配审核人时整张工作表都要拦截"""
        worksheet = DummyWorksheet("WS-001", "reviewer01", [
            DummyAnalysis("A1", "to_be_verified"),
        ])

        selected, errors = review_logic.collect_verifiable_analyses(
            [worksheet], "reviewer02")

        self.assertEqual([], selected)
        self.assertEqual([u"工作表 WS-001 未分配给当前审核人"], errors)

    def test_collect_verifiable_analyses_requires_pending_items(self):
        """工作表里没有待复核分析项时应返回明确错误"""
        worksheet = DummyWorksheet("WS-001", "reviewer01", [
            DummyAnalysis("A1", "verified"),
        ])

        selected, errors = review_logic.collect_verifiable_analyses(
            [worksheet], "reviewer01")

        self.assertEqual([], selected)
        self.assertEqual([u"工作表 WS-001 没有可审核的分析项"], errors)
