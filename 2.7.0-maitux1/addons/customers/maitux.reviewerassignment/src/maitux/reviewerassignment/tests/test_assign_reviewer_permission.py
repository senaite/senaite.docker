# -*- coding: utf-8 -*-
"""审核人指派权限与候选过滤测试

拆成两个 permission 的理由：rolemap 是按角色全站授予的，只给一个就意味着
任意 Analyst 能改任意工作表的审核人 —— Care 的 RestrictWorksheetUsersAccess=False
让 Analyst 能访问所有工作表，SENAITE 侧没有归属边界。
"""

import imp
import os
import unittest
from xml.etree import ElementTree


BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
review_logic = imp.load_source(
    "ra_review_logic_perm", os.path.join(BASE, "review_logic.py"))
ROLEMAP = os.path.join(BASE, "profiles", "default", "rolemap.xml")
ZCML = os.path.join(BASE, "configure.zcml")
PERMISSIONS = os.path.join(BASE, "permissions.py")
TEMPLATE = os.path.join(BASE, "browser", "templates", "manage_results.pt")
VIEW = os.path.join(BASE, "browser", "manage_results.py")


class TestCanAssignReviewer(unittest.TestCase):
    """归属判定：自己的放行，别人的要更高权限"""

    def test_no_base_permission_is_denied(self):
        """没有基础权限，一律拒绝"""
        self.assertFalse(review_logic.can_assign_reviewer(True, False, True))
        self.assertFalse(review_logic.can_assign_reviewer(False, False, True))

    def test_own_worksheet_is_allowed(self):
        """自己是分析员的工作表，有基础权限即可"""
        self.assertTrue(review_logic.can_assign_reviewer(True, True, False))

    def test_other_worksheet_needs_reassign_permission(self):
        """别人的工作表，必须有 Reassign Any Reviewer"""
        self.assertFalse(review_logic.can_assign_reviewer(False, True, False))
        self.assertTrue(review_logic.can_assign_reviewer(False, True, True))


class TestEditableState(unittest.TestCase):
    """状态判定"""

    STATES = ("open", "to_be_verified")

    def test_open_and_to_be_verified_are_editable(self):
        """录入中与待审核都可改 —— 与 senaite.core 的 edit_states 一致"""
        self.assertTrue(
            review_logic.is_reviewer_editable_state("open", self.STATES))
        self.assertTrue(
            review_logic.is_reviewer_editable_state("to_be_verified", self.STATES))

    def test_verified_is_not_editable(self):
        """已审核后不可改"""
        self.assertFalse(
            review_logic.is_reviewer_editable_state("verified", self.STATES))

    def test_empty_state_is_not_editable(self):
        """状态取不到时不放行"""
        self.assertFalse(review_logic.is_reviewer_editable_state("", self.STATES))
        self.assertFalse(review_logic.is_reviewer_editable_state(None, self.STATES))


class TestExcludeSubmitter(unittest.TestCase):
    """是否需要把未来的提交人剔出候选"""

    def test_all_allow_self_verification_means_no_exclusion(self):
        """全部允许自审 → 不用剔除"""
        self.assertFalse(review_logic.should_exclude_submitter([True, True]))

    def test_any_disallow_means_exclusion(self):
        """任一不允许自审 → 剔除（保守取向）"""
        self.assertTrue(review_logic.should_exclude_submitter([True, False]))
        self.assertTrue(review_logic.should_exclude_submitter([False]))

    def test_no_analyses_means_no_exclusion(self):
        """没有分析项时无从判断，不剔除"""
        self.assertFalse(review_logic.should_exclude_submitter([]))
        self.assertFalse(review_logic.should_exclude_submitter(None))


class TestFilterCandidates(unittest.TestCase):
    """候选名单过滤"""

    CANDIDATES = [("analyst1", u"张三"), ("analyst2", u"李四")]

    def test_excludes_the_given_user(self):
        """剔除指定用户"""
        got = review_logic.filter_reviewer_candidates(
            self.CANDIDATES, "analyst1")
        self.assertEqual([c[0] for c in got], ["analyst2"])

    def test_empty_exclusion_keeps_everyone(self):
        """不需要剔除时原样返回"""
        for empty in ("", None, "   "):
            got = review_logic.filter_reviewer_candidates(
                self.CANDIDATES, empty)
            self.assertEqual([c[0] for c in got], ["analyst1", "analyst2"])

    def test_unknown_user_changes_nothing(self):
        """要剔除的人不在名单里时无副作用"""
        got = review_logic.filter_reviewer_candidates(
            self.CANDIDATES, "someone_else")
        self.assertEqual([c[0] for c in got], ["analyst1", "analyst2"])


class TestRolemap(unittest.TestCase):
    """两个 permission 的角色配置"""

    def setUp(self):
        root = ElementTree.parse(ROLEMAP).getroot()
        self.perms = {}
        for perm in root.iter("permission"):
            self.perms[perm.get("name")] = sorted(
                r.get("name") for r in perm.findall("role"))

    def test_assign_reviewer_includes_analyst(self):
        """实验员必须能给自己的工作表选审核人 —— 业务硬要求"""
        roles = self.perms.get("maitux.reviewerassignment: Assign Reviewer")
        self.assertIsNotNone(roles)
        self.assertIn("Analyst", roles)
        self.assertIn("LabManager", roles)
        self.assertIn("Manager", roles)

    def test_permissions_are_registered_in_zcml(self):
        """光有 rolemap.xml 不够 -- 未注册的权限会让 manage_permission 报
        "The permission ... is invalid"，rolemap 导入直接失败。"""
        with open(ZCML, "rb") as handle:
            source = handle.read().decode("utf-8")
        for name in ("maitux.reviewerassignment: Assign Reviewer",
                     "maitux.reviewerassignment: Reassign Any Reviewer"):
            self.assertIn('title="%s"' % name, source)

    def test_permission_constants_live_in_permissions_module(self):
        """常量与 rolemap / zcml 中的字符串必须完全一致"""
        with open(PERMISSIONS, "rb") as handle:
            source = handle.read().decode("utf-8")
        self.assertIn(
            'AssignReviewer = "maitux.reviewerassignment: Assign Reviewer"',
            source)
        self.assertIn(
            'ReassignAnyReviewer = "maitux.reviewerassignment: Reassign Any Reviewer"',
            source)

    def test_reassign_any_excludes_analyst(self):
        """改别人的工作表不能给实验员 —— 否则归属边界形同虚设"""
        roles = self.perms.get(
            "maitux.reviewerassignment: Reassign Any Reviewer")
        self.assertIsNotNone(roles)
        self.assertNotIn("Analyst", roles)
        self.assertEqual(roles, ["LabManager", "Manager"])


class TestTemplateAndViewWiring(unittest.TestCase):
    """模板与写入路径都必须走新判定"""

    def test_reviewer_block_uses_new_check(self):
        """审核人块的 3 处条件改用 can_assign_reviewer"""
        with open(TEMPLATE, "rb") as handle:
            source = handle.read().decode("utf-8")
        self.assertEqual(source.count("view/can_assign_reviewer"), 3)

    def test_analyst_and_instrument_blocks_untouched(self):
        """Analyst 与 Instrument 是 core 的字段，仍用 is_assignment_allowed"""
        with open(TEMPLATE, "rb") as handle:
            source = handle.read().decode("utf-8")
        self.assertEqual(source.count("view/is_assignment_allowed"), 4)

    def test_write_path_validates_before_writing(self):
        """写入路径必须先校验，不能只靠模板控制显隐"""
        with open(VIEW, "rb") as handle:
            source = handle.read().decode("utf-8")
        handler = source.split("def handle_reviewer_assignment", 1)[1]
        guard_pos = handler.find("if not self.can_assign_reviewer():")
        write_pos = handler.find("set_reviewer_userid(")
        self.assertNotEqual(guard_pos, -1, "写入路径缺少权限校验")
        self.assertNotEqual(write_pos, -1)
        self.assertLess(guard_pos, write_pos, "校验必须在写入之前")

    def test_write_path_validates_candidate(self):
        """选中的人必须在候选名单内，挡住直接构造请求"""
        with open(VIEW, "rb") as handle:
            source = handle.read().decode("utf-8")
        self.assertIn("allowed = [item[0] for item in self.get_reviewer_options()]",
                      source)


if __name__ == "__main__":
    unittest.main()
