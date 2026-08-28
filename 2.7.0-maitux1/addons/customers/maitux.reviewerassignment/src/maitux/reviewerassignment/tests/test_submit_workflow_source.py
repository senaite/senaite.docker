# -*- coding: utf-8 -*-
"""提交分配流程源码回归测试"""

import os
import unittest


WORKFLOW_SOURCE = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, "browser", "workflow.py"))


class TestSubmitWorkflowSource(unittest.TestCase):
    """避免再次把 analysis 提交误当成 worksheet 提交"""

    def test_submit_adapter_uses_context_for_last_submit_check(self):
        """提交前要基于 worksheet 上的审核人做校验

        原来这里还断言 `set_reviewer_userid(analysis, reviewer_userid)` ——
        即把审核人复制一份写到每个分析项上。那份副本从来没被任何代码读过
        （guard_analysis 读的始终是工作表上的值），改工作表审核人时也不会同步，
        已作为数据一致性清理移除。「不得再出现」由
        test_uninstall_source.TestNoDeadAnalysisCopy 断言。
        """
        with open(WORKFLOW_SOURCE, "r") as handle:
            source = handle.read()

        self.assertIn("reviewer_userid = get_reviewer_userid(self.context)", source)
        self.assertIn("if not has_selected_reviewer(reviewer_userid):", source)

    def test_submit_adapter_no_longer_uses_prompt_flow(self):
        """简单方案下不应再保留弹窗分配流程残留"""
        with open(WORKFLOW_SOURCE, "r") as handle:
            source = handle.read()

        self.assertNotIn("WorksheetSubmitPromptView", source)
        self.assertNotIn("pending_submit_payload", source)
        self.assertNotIn("should_prompt_submit_reviewer", source)
