# -*- coding: utf-8 -*-
"""受控签名含义与含义词表（缺口 4）的语义测试。

只测 services/rules.py 的纯函数，不需要 Zope。
"""
import importlib.util
import os
import unittest


def load_rules_module():
    file_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "services", "rules.py"))
    spec = importlib.util.spec_from_file_location("test_rules_module", file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestDefaultMeanings(unittest.TestCase):

    def setUp(self):
        self.rules = load_rules_module()

    def test_meaning_follows_the_transition_not_the_outcome(self):
        """含义描述签名人的角色，所以 reject 不该是 Approval。"""
        self.assertEqual(self.rules.default_meaning_for("verify"), u"Approval")
        self.assertEqual(self.rules.default_meaning_for("submit"), u"Authorship")
        self.assertEqual(
            self.rules.default_meaning_for("reject"), u"Responsibility")
        self.assertNotEqual(
            self.rules.default_meaning_for("reject"), u"Approval")

    def test_unknown_transition_has_no_suggestion(self):
        self.assertEqual(self.rules.default_meaning_for("whatever"), u"")
        self.assertEqual(self.rules.default_meaning_for(None), u"")


class TestRuleMeaningNormalisation(unittest.TestCase):

    def setUp(self):
        self.rules = load_rules_module()

    def test_configured_meaning_is_kept_verbatim(self):
        """现场按 SOP 改写的措辞不能被建议值冲掉。"""
        rule = self.rules.normalize_rule({
            "portal_type": u"Analysis",
            "transition_id": u"verify",
            "meaning": u"复核批准",
        })
        self.assertEqual(rule["meaning"], u"复核批准")

    def test_empty_meaning_falls_back_to_the_suggestion(self):
        """升级前保存的老规则没有这个字段，也要拿到合理的含义。"""
        rule = self.rules.normalize_rule({
            "portal_type": u"Analysis",
            "transition_id": u"reject",
        })
        self.assertEqual(rule["meaning"], u"Responsibility")

    def test_meaning_survives_a_dumps_loads_round_trip(self):
        rules = [{
            "portal_type": u"Analysis",
            "transition_id": u"verify",
            "meaning": u"Approval",
        }]
        text = self.rules.dumps_policy_rules(rules)
        restored = self.rules.loads_policy_rules(text)
        self.assertEqual(len(restored), 1)
        self.assertEqual(restored[0]["meaning"], u"Approval")


class TestMeaningVocabulary(unittest.TestCase):

    def setUp(self):
        self.rules = load_rules_module()

    def test_one_per_line_trimmed_and_deduped(self):
        raw = u"  Approval  \n\nReview\nApproval\n   \nResponsibility\n"
        self.assertEqual(
            self.rules.parse_meaning_vocabulary(raw),
            [u"Approval", u"Review", u"Responsibility"])

    def test_order_is_preserved_because_it_drives_the_dropdown(self):
        self.assertEqual(
            self.rules.parse_meaning_vocabulary(u"Zeta\nAlpha\nMiddle"),
            [u"Zeta", u"Alpha", u"Middle"])

    def test_empty_input_falls_back_to_the_default_list(self):
        """词表不能变成空的，否则规则表的下拉里一个选项都没有。"""
        for raw in (u"", u"   \n  \n", None):
            self.assertEqual(
                self.rules.parse_meaning_vocabulary(raw),
                list(self.rules.DEFAULT_MEANING_VOCABULARY))

    def test_round_trip_is_stable(self):
        text = self.rules.dumps_meaning_vocabulary(
            [u"Approval", u"  Review  ", u"Approval"])
        self.assertEqual(text, u"Approval\nReview")
        self.assertEqual(
            self.rules.parse_meaning_vocabulary(text),
            [u"Approval", u"Review"])

    def test_non_ascii_terms_survive(self):
        """现场按 SOP 用中文措辞也要能存。"""
        self.assertEqual(
            self.rules.parse_meaning_vocabulary(u"复核批准\n授权发布"),
            [u"复核批准", u"授权发布"])


class TestControlPanelTemplateIds(unittest.TestCase):
    """控制面板模板的 element id 必须唯一。

    这条测试是为一个真实 bug 写的：喂给 JS 的 JSON script 标签和 Base Settings
    里的 textarea 用了同一个 id，getElementById 返回了 textarea，JSON.parse 失败
    静默回落成空列表，于是规则表的 Meaning 下拉一个选项都没有，已配好的
    "Approval" 被标成 "(not in the list)"。全程无报错。
    """

    def test_ids_are_unique(self):
        import collections
        import io as _io
        import re

        path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "browser", "templates",
            "controlpanel.pt"))
        with _io.open(path, "r", encoding="utf-8") as handle:
            source = handle.read()

        ids = re.findall(r'id="([^"]+)"', source)
        duplicates = sorted(
            name for name, count in collections.Counter(ids).items() if count > 1)
        self.assertEqual(duplicates, [], "duplicate element ids: %r" % duplicates)

    def test_script_block_is_ascii_only(self):
        """ZPT 的 <script> 块里不能出现非 ASCII 字符。

        又一个真实 bug：下拉的空白项写成 blank.text = '<em dash>'，ZPT 把它
        转成数字实体 &#8212;，而 HTML5 规定 <script> 内是 raw text、浏览器不做
        实体解码，于是下拉里赫然显示 "&#8212;" 七个字符。
        非 ASCII 一律用 String.fromCharCode() 或 JS 的 unicode 转义写法。
        """
        import io as _io

        path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "browser", "templates",
            "controlpanel.pt"))
        with _io.open(path, "r", encoding="utf-8") as handle:
            source = handle.read()

        marker = '<script type="text/javascript">'
        self.assertIn(marker, source)
        script = source[source.index(marker):]
        offenders = sorted(set(c for c in script if ord(c) > 127))
        self.assertEqual(
            offenders, [],
            "non-ASCII in the script block will be entity-encoded: %r"
            % (offenders,))


if __name__ == "__main__":
    unittest.main()
