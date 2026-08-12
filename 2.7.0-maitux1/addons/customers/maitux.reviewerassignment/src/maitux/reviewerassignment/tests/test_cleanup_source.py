# -*- coding: utf-8 -*-
"""旧提交流程清理回归测试"""

import os
import unittest


BROWSER_ZCML = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, "browser", "configure.zcml"))
REVIEW_LOGIC = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, "review_logic.py"))


class TestCleanupSource(unittest.TestCase):
    """确保旧弹窗提交流程已被移除"""

    def test_browser_zcml_no_longer_registers_submit_prompt(self):
        """不再注册 reviewer-submit-prompt 页面"""
        with open(BROWSER_ZCML, "r") as handle:
            source = handle.read()

        self.assertNotIn('name="reviewer-submit-prompt"', source)
        self.assertNotIn("browser.submit_prompt.WorksheetSubmitPromptView", source)

    def test_review_logic_no_longer_contains_last_submit_prompt_logic(self):
        """纯逻辑模块不再保留最后一次提交弹窗判断"""
        with open(REVIEW_LOGIC, "r") as handle:
            source = handle.read()

        self.assertNotIn("def should_prompt_submit_reviewer", source)
