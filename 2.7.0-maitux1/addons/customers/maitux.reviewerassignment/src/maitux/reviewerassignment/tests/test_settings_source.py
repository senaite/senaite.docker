# -*- coding: utf-8 -*-
"""站点级开关的回归测试

三条业务规则原来硬编码，站点无法调整。做成开关后有两条硬要求：

1. **默认值必须与硬编码时期完全一致** —— 升级上来的站点行为不能变；
2. **读取失败必须回落默认值，绝不抛异常** —— 这些开关在 guard 求值路径上被读到，
   一个异常就能把整条工作流卡死。
"""

import imp
import io
import os
import unittest


BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
SETTINGS = os.path.join(BASE, "settings.py")
GUARD = os.path.join(BASE, "guards", "reviewer.py")
ASSIGNMENT = os.path.join(BASE, "assignment.py")
INTERFACES = os.path.join(BASE, "interfaces.py")
CONTROLPANEL = os.path.join(BASE, "browser", "controlpanel.py")
ZCML = os.path.join(BASE, "browser", "configure.zcml")
CONFIGLET = os.path.join(BASE, "profiles", "default", "controlpanel.xml")

SWITCHES = (
    "require_reviewer_on_worksheet_submit",
    "require_reviewer_on_analysis_submit",
    "restrict_verify_to_assigned_reviewer",
    "exclude_submitter_from_reviewers",
)


def read(path):
    with io.open(path, encoding="utf-8") as handle:
        return handle.read()


class TestDefaults(unittest.TestCase):
    """默认值必须保持原有行为"""

    def test_all_switches_default_to_true(self):
        """全部默认开启 == 硬编码时期的行为，升级不改变行为"""
        source = read(SETTINGS)
        block = source.split("DEFAULTS = {", 1)[1].split("}", 1)[0]
        for name in SWITCHES:
            self.assertIn('"%s": True' % name, block)

    def test_schema_defaults_match(self):
        """接口 schema 的 default 也必须是 True，两处不能打架

        按「下一个字段名」切块，而不是按第一个右括号 —— description 是多行括号
        表达式，按括号切会在字段声明中间截断。
        """
        source = read(INTERFACES)
        for index, name in enumerate(SWITCHES):
            chunk = source.split(name + " = schema.Bool", 1)[1]
            if index + 1 < len(SWITCHES):
                chunk = chunk.split(SWITCHES[index + 1], 1)[0]
            self.assertIn("default=True", chunk,
                          "%s 的 schema 默认值不是 True" % name)


class TestFailSafeReading(unittest.TestCase):
    """读取失败必须回落默认值"""

    def test_get_setting_swallows_exceptions(self):
        """任何异常都回落默认值，不能抛到 guard 里"""
        source = read(SETTINGS)
        block = source.split("def get_setting", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("except Exception:", block)
        self.assertIn("return default", block)

    def test_none_falls_back_to_default(self):
        """记录存在但值为 None 时也要回落"""
        source = read(SETTINGS)
        block = source.split("def get_setting", 1)[1].split("\ndef ", 1)[0]
        self.assertIn("if value is None:", block)


class TestSwitchesAreWired(unittest.TestCase):
    """开关必须真的接到业务规则上，否则就是个摆设"""

    def test_worksheet_submit_rule_is_switchable(self):
        self.assertIn("require_reviewer_on_worksheet_submit()", read(GUARD))

    def test_analysis_submit_rule_is_switchable(self):
        self.assertIn("require_reviewer_on_analysis_submit()", read(GUARD))

    def test_verify_restriction_is_switchable(self):
        self.assertIn("restrict_verify_to_assigned_reviewer()", read(GUARD))

    def test_candidate_filter_is_switchable(self):
        self.assertIn("exclude_submitter_from_reviewers()", read(ASSIGNMENT))

    def test_site_scoping_still_runs_first(self):
        """站点级收口必须仍在最前面 —— 未安装站点连开关都不该读"""
        source = read(GUARD)
        guard = source.split("def guard(self, transition)", 1)[1]
        guard = guard.split("\n    def ", 1)[0]
        self.assertIn("if not is_installed_in_current_site():", guard)


class TestControlPanel(unittest.TestCase):
    """控制面板"""

    def test_view_is_registered_with_layer(self):
        """必须绑 browser layer，否则未安装站点也能访问"""
        source = read(ZCML)
        self.assertIn("maitux-reviewerassignment-controlpanel", source)
        chunk = source.split("maitux-reviewerassignment-controlpanel", 1)[1]
        chunk = chunk.split("/>", 1)[0]
        self.assertIn(
            "maitux.reviewerassignment.interfaces.IReviewerAssignmentLayer",
            chunk)

    def test_panel_exposes_all_switches(self):
        """四个开关都要出现在面板上"""
        source = read(CONTROLPANEL)
        for name in SWITCHES:
            self.assertIn('"%s"' % name, source)

    def test_configlet_title_is_ascii_only(self):
        """configlet 标题必须是纯 ASCII

        Products/CMFPlone/exportimport/controlpanel.py:123 对 title 做 str()，
        含中文会在 profile 导入时抛 UnicodeEncodeError，整个安装失败。
        中文标题放在面板模板的 H1 里。
        """
        from xml.etree import ElementTree
        configlet = ElementTree.parse(CONFIGLET).getroot().find("configlet")
        self.assertIsNotNone(configlet)
        title = configlet.get("title") or ""
        self.assertTrue(title)
        for char in title:
            self.assertLess(
                ord(char), 128,
                u"configlet title 含非 ASCII 字符 %r，会导致 profile 导入失败"
                % char)

    def test_panel_shows_prerequisite_status(self):
        """面板要显示站点前置条件状态，而不是只写进安装日志"""
        source = read(CONTROLPANEL)
        self.assertIn("def get_prerequisite_status", source)
        self.assertIn("getAllowToSubmitNotAssigned", source)


if __name__ == "__main__":
    unittest.main()
