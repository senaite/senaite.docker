# -*- coding: utf-8 -*-
"""审核分配核心判定测试"""

import imp
import os
import unittest


MODULE_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, "review_logic.py"))
review_logic = imp.load_source("review_logic", MODULE_PATH)


class TestReviewAssignmentGuards(unittest.TestCase):
    """校验审核人必填和审核人匹配规则"""

    def test_has_selected_reviewer_rejects_empty_values(self):
        """空值、空白值都不允许提交工作表"""
        self.assertFalse(review_logic.has_selected_reviewer(""))
        self.assertFalse(review_logic.has_selected_reviewer(None))
        self.assertFalse(review_logic.has_selected_reviewer("   "))

    def test_has_selected_reviewer_accepts_text_userid(self):
        """只要保存了用户 id，就认为已分配审核人"""
        self.assertTrue(review_logic.has_selected_reviewer("reviewer01"))

    def test_can_submit_analysis_in_worksheet_requires_reviewer(self):
        """工作表内分析项提交前必须先给工作表分配审核人"""
        allowed = review_logic.can_submit_analysis_in_worksheet(True, "")
        self.assertFalse(allowed)

    def test_can_submit_analysis_without_worksheet_is_not_blocked(self):
        """不属于工作表的分析项提交不受审核人规则影响"""
        allowed = review_logic.can_submit_analysis_in_worksheet(False, "")
        self.assertTrue(allowed)

    def test_can_submit_analysis_in_worksheet_accepts_selected_reviewer(self):
        """工作表已分配审核人时允许分析项提交"""
        allowed = review_logic.can_submit_analysis_in_worksheet(True, "reviewer01")
        self.assertTrue(allowed)

    def test_is_assigned_verifier_requires_verifier_role(self):
        """只有审核人角色才允许执行审核"""
        allowed = review_logic.is_assigned_verifier(
            "reviewer01", ["Analyst"], "reviewer01")
        self.assertFalse(allowed)

    def test_is_assigned_verifier_requires_same_user(self):
        """角色正确但不是被分配人时也不能审核"""
        allowed = review_logic.is_assigned_verifier(
            "reviewer02", ["Verifier"], "reviewer01")
        self.assertFalse(allowed)

    def test_is_assigned_verifier_accepts_exact_match(self):
        """审核人角色且用户匹配时允许审核"""
        allowed = review_logic.is_assigned_verifier(
            "reviewer01", ["Verifier", "Authenticated"], "reviewer01")
        self.assertTrue(allowed)
