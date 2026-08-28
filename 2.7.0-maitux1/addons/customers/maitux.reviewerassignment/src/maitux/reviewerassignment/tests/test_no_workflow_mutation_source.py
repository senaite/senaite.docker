# -*- coding: utf-8 -*-
"""不得改动 live workflow 的回归测试

本 addon 曾经用 state.setPermission() / state.transitions 直接写 live workflow，
把 analysis "to_be_verified" 的 Verify 权限从原生的
[LabManager, Manager, Verifier] 收窄成 [Verifier]。

该权限归 maitux.workflow 管（它设的正是原生值）。两个 addon 同写一个权限，
谁的 profile 后跑谁赢，导致同一套代码在不同站点表现不一致 —— 本机四个站点里
只有 Care 中招。

这些断言防止同类改动再次混进来。
"""

import io
import os
import unittest


SETUPHANDLERS = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, "setuphandlers.py"))


def read_setuphandlers():
    """只返回代码行，剔除注释行。

    setuphandlers.py 顶部保留了一段解释「为什么删掉 setup_workflows」的注释，
    里面必然出现 setPermission / state.transitions / 权限名等字样。断言要检查的是
    真实代码，不是这段说明文字 —— 否则注释本身会把测试搞失败。
    """
    with io.open(SETUPHANDLERS, encoding="utf-8") as handle:
        lines = handle.readlines()
    return u"".join(
        line for line in lines if not line.lstrip().startswith(u"#"))


class TestNoWorkflowMutation(unittest.TestCase):
    """setuphandlers 不得触碰 workflow 的权限与状态出口"""

    def test_setup_workflows_is_gone(self):
        """setup_workflows() 及其两个 helper 必须已删除"""
        source = read_setuphandlers()
        self.assertNotIn("def setup_workflows", source)
        self.assertNotIn("def ensure_state_transitions", source)
        self.assertNotIn("def ensure_state_permission_setup", source)

    def test_run_install_steps_no_longer_calls_setup_workflows(self):
        """安装编排里不得再调用 setup_workflows()"""
        self.assertNotIn("setup_workflows()", read_setuphandlers())

    def test_no_permission_mutation_api(self):
        """不得再出现直接写 live workflow 的 API"""
        source = read_setuphandlers()
        self.assertNotIn("setPermission", source)
        self.assertNotIn("state.transitions", source)

    def test_no_workflow_permission_constants(self):
        """不得再持有 workflow 权限常量 —— 它们不归本 addon 管"""
        source = read_setuphandlers()
        for name in (
            "senaite.core: Transition: Verify",
            "senaite.core: Transition: Retest",
            "senaite.core: Transition: Retract",
            "senaite.core: Transition: Reject Analysis",
        ):
            self.assertNotIn(name, source)

    def test_no_workflow_ids(self):
        """不得再引用 workflow id"""
        source = read_setuphandlers()
        self.assertNotIn("senaite_analysis_workflow", source)
        self.assertNotIn("senaite_worksheet_workflow", source)

    def test_portal_workflow_tool_is_not_acquired(self):
        """不得再取 portal_workflow 工具"""
        self.assertNotIn('get_tool("portal_workflow")', read_setuphandlers())

    def test_verifier_role_still_used_for_container_permissions(self):
        """VERIFIER_ROLE 仍用于根容器权限，不能被顺手删掉"""
        source = read_setuphandlers()
        self.assertIn("VERIFIER_ROLE", source)
        self.assertIn('roles = [VERIFIER_ROLE, "LabManager", "Manager", "Owner"]',
                      source)


if __name__ == "__main__":
    unittest.main()
