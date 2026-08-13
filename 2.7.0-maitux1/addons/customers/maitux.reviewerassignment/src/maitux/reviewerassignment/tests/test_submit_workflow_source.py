# -*- coding: utf-8 -*-
"""提交分配流程源码回归测试"""

import os
import unittest


WORKFLOW_SOURCE = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, "browser", "workflow.py"))


class TestSubmitWorkflowSource(unittest.TestCase):
    """避免再次把 analysis 提交误当成 worksheet 提交"""

    def test_submit_adapter_uses_context_for_last_submit_check(self):
        """提交前要基于 worksheet 审核人做校验并同步写入 analysis"""
        with open(WORKFLOW_SOURCE, "r") as handle:
            source = handle.read()

        self.assertIn("reviewer_userid = get_reviewer_userid(self.context)", source)
        self.assertIn("if not has_selected_reviewer(reviewer_userid):", source)
        self.assertIn("set_reviewer_userid(analysis, reviewer_userid)", source)

    def test_submit_adapter_no_longer_uses_prompt_flow(self):
        """简单方案下不应再保留弹窗分配流程残留"""
        with open(WORKFLOW_SOURCE, "r") as handle:
            source = handle.read()

        self.assertNotIn("WorksheetSubmitPromptView", source)
        self.assertNotIn("pending_submit_payload", source)
        self.assertNotIn("should_prompt_submit_reviewer", source)
