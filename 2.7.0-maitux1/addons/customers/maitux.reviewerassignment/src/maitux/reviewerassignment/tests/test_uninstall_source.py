# -*- coding: utf-8 -*-
"""卸载能力回归测试

原则：卸载 = 拆结构与行为，不碰业务数据。

- 结构/行为层（behavior、catalog 索引、类型约束、侧边栏、browserlayer）必须还原；
- 业务数据层（根容器及其内容、工作表上已保存的审核人字段值）绝不动。

审核人字段值在 behavior 停用后前端不再显示，但仍完整保存在 ZODB 里，
重装即恢复 —— 有意为之的「孤儿属性」策略。
"""

import io
import os
import unittest
from xml.etree import ElementTree


BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
SETUPHANDLERS = os.path.join(BASE, "setuphandlers.py")
UNINSTALL_DIR = os.path.join(BASE, "profiles", "uninstall")
WORKFLOW = os.path.join(BASE, "browser", "workflow.py")


def read_code(path):
    """只返回代码行，剔除注释行"""
    with io.open(path, encoding="utf-8") as handle:
        lines = handle.readlines()
    return u"".join(
        line for line in lines if not line.lstrip().startswith(u"#"))


class TestUninstallCoverage(unittest.TestCase):
    """安装做了什么，卸载就要还原什么"""

    def setUp(self):
        self.source = read_code(SETUPHANDLERS)

    def test_teardown_steps_exist(self):
        """四个还原步骤都要有"""
        for name in ("teardown_sidebar", "teardown_behaviors",
                     "teardown_catalog", "teardown_type_constraints"):
            self.assertIn("def %s" % name, self.source)

    def test_all_teardowns_are_wired(self):
        """都要挂进 uninstall_handler，漏一个就是静默失败"""
        handler = self.source.split("def uninstall_handler", 1)[1]
        handler = handler.split("\ndef teardown_sidebar", 1)[0]
        for name in ("teardown_sidebar()", "teardown_behaviors()",
                     "teardown_catalog()", "teardown_type_constraints()"):
            self.assertIn(name, handler)

    def test_behavior_is_disabled(self):
        """停用 behavior，而不是删字段值"""
        self.assertIn("disable_behavior", self.source)

    def test_catalog_index_and_column_are_removed(self):
        """索引和列都要摘掉"""
        self.assertIn("del_index", self.source)
        self.assertIn("del_column", self.source)

    def test_root_container_is_never_deleted(self):
        """根容器是业务数据，卸载绝不能删"""
        self.assertNotIn("manage_delObjects", self.source)
        self.assertNotIn("delattr", self.source)

    def test_install_and_uninstall_are_symmetric(self):
        """安装的每个结构性步骤都有对应的还原步骤"""
        pairs = [
            ("setup_sidebar", "teardown_sidebar"),
            ("setup_behaviors", "teardown_behaviors"),
            ("setup_catalog", "teardown_catalog"),
            ("setup_type_constraints", "teardown_type_constraints"),
        ]
        for setup_name, teardown_name in pairs:
            self.assertIn("def %s" % setup_name, self.source)
            self.assertIn("def %s" % teardown_name, self.source)


class TestUninstallProfile(unittest.TestCase):
    """卸载 profile 的内容"""

    def test_browserlayer_is_removed(self):
        """必须注销 browser layer

        不注销的话，卸载后绑在该 layer 上的
        WorkflowActionSubmitReviewerAdapter 依旧活着，仍会拦住 submit。
        """
        path = os.path.join(UNINSTALL_DIR, "browserlayer.xml")
        self.assertTrue(os.path.exists(path), "缺少 uninstall/browserlayer.xml")
        layer = ElementTree.parse(path).getroot().find("layer")
        self.assertIsNotNone(layer)
        self.assertEqual(layer.get("remove"), "True")
        self.assertEqual(
            layer.get("interface"),
            "maitux.reviewerassignment.interfaces.IReviewerAssignmentLayer")

    def test_no_dependency_on_the_install_profile(self):
        """卸载 profile 不得依赖安装 profile —— 方向是反的"""
        path = os.path.join(UNINSTALL_DIR, "metadata.xml")
        root = ElementTree.parse(path).getroot()
        deps = [d.text for d in root.iter("dependency")]
        self.assertEqual(deps, [])


class TestNoDeadAnalysisCopy(unittest.TestCase):
    """分析项上的审核人副本已移除"""

    def test_submit_no_longer_copies_reviewer_to_analyses(self):
        """审核人是工作表级属性，不按分析项存

        那份副本从来没被读过（guard 读的是工作表上的值），改工作表审核人时
        也不会同步，留着只是数据不一致的隐患。
        """
        source = read_code(WORKFLOW)
        self.assertNotIn("set_reviewer_userid", source)


if __name__ == "__main__":
    unittest.main()
