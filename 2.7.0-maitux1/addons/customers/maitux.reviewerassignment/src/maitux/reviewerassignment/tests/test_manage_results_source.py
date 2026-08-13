# -*- coding: utf-8 -*-
"""管理结果页源码回归测试"""

import os
import unittest


TEMPLATE_SOURCE = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, "browser", "templates",
    "manage_results.pt"))
VIEW_SOURCE = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, "browser", "manage_results.py"))
INTERFACE_SOURCE = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, "interfaces.py"))


class TestManageResultsSource(unittest.TestCase):
    """确保管理结果页包含审核人分配入口"""

    def test_manage_results_template_contains_reviewer_controls(self):
        """检验人后面要出现审核人下拉框和 Apply 按钮"""
        with open(TEMPLATE_SOURCE, "r") as handle:
            source = handle.read()

        self.assertIn('name="reviewer_userid"', source)
        self.assertIn('name="reviewer_assignment_apply"', source)
        self.assertIn("view/get_reviewer_options", source)

    def test_manage_results_view_handles_reviewer_apply(self):
        """管理结果页视图需要处理审核人 Apply 动作"""
        with open(VIEW_SOURCE, "r") as handle:
            source = handle.read()

        self.assertIn("def handle_reviewer_assignment(self):", source)
        self.assertIn('self.request.get("reviewer_assignment_apply")', source)
        self.assertIn('self.request.form.get("reviewer_userid")', source)

    def test_browser_layer_extends_senaite_core_layer(self):
        """浏览器层要继承 ISenaiteCore，确保覆盖 core 的同名页面"""
        with open(INTERFACE_SOURCE, "r") as handle:
            source = handle.read()

        self.assertIn("from senaite.core.interfaces import ISenaiteCore", source)
        self.assertIn("class IReviewerAssignmentLayer(ISenaiteCore):", source)
