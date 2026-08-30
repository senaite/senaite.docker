# -*- coding: utf-8 -*-
"""Calculation Interim Fields 格式化测试"""

import imp
import os
import unittest


FORMATTER_SOURCE = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, "browser", "formatter.py"))


def load_formatter_module():
    """兼容 Python 2.7 的模块加载方式"""
    return imp.load_source("maitux_audittrail_formatter_test", FORMATTER_SOURCE)


class TestInterimFieldsFormatter(unittest.TestCase):
    """确保 Interim Fields 可以渲染成可读结构"""

    def test_render_interim_fields_html_contains_key_columns(self):
        """应把关键字段渲染成表格，而不是原始 JSON 串"""
        module = load_formatter_module()
        html = module.render_interim_fields_html([
            {
                "keyword": "CA_RF",
                "title": u"Ca_Rf",
                "result_type": "calculated",
                "value": "1.0",
                "formula": "[CA_SampleWeight] / [CA_SampleVolume]",
                "unit": "%",
                "choices": "",
                "allow_empty": False,
                "report": True,
                "hidden": False,
                "wide": True,
            }
        ])

        self.assertIn(u"关键字", html)
        self.assertIn(u"字段标题", html)
        self.assertIn(u"公式", html)
        self.assertIn(u"CA_RF", html)
        self.assertIn(u"Ca_Rf", html)
        self.assertIn(u"[CA_SampleWeight] / [CA_SampleVolume]", html)
        self.assertNotIn(u'["keyword"', html)

    def test_render_interim_fields_html_handles_empty_value(self):
        """空值也要返回可读提示，避免界面空白"""
        module = load_formatter_module()
        html = module.render_interim_fields_html([])

        self.assertIn(u"未设置", html)

    def test_render_interim_fields_html_accepts_pair_list_rows(self):
        """兼容审计 diff 中可能出现的键值对列表结构"""
        module = load_formatter_module()
        html = module.render_interim_fields_html([
            [
                ["allow_empty", "True"],
                ["apply_wide", "True"],
                ["choices", ""],
                ["formula", "<NO_VALUE>"],
                ["hidden", "False"],
                ["keyword", "NM"],
                ["report", "True"],
                ["result_type", "numeric"],
                ["title", "Nett Mass"],
                ["unit", "g"],
                ["value", "0"],
            ]
        ])

        self.assertIn(u"NM", html)
        self.assertIn(u"Nett Mass", html)
        self.assertIn(u"全局应用", html)


class TestDefaultValueFormatter(unittest.TestCase):
    """多选类型的默认值是 JSON 串，中文不能露成 \\uXXXX"""

    def test_json_list_value_is_decoded(self):
        """json.dumps 的 ensure_ascii 转义必须解回中文"""
        module = load_formatter_module()
        value = module.format_default_value(
            u'["\\u672a\\u77e5\\u6742\\u8d28", "Z7"]')

        self.assertEqual(value, u"未知杂质、Z7")
        self.assertNotIn(u"\\u672a", value)

    def test_real_list_value_is_joined(self):
        """快照里已经是列表时也要拼成可读文本"""
        module = load_formatter_module()

        self.assertEqual(
            module.format_default_value([u"未知杂质", u"Z7"]), u"未知杂质、Z7")

    def test_plain_value_is_untouched(self):
        """普通标量原样返回，不要被当成 JSON 处理"""
        module = load_formatter_module()

        self.assertEqual(module.format_default_value("0.5"), u"0.5")
        self.assertEqual(module.format_default_value(None), u"")

    def test_broken_json_falls_back_to_raw_text(self):
        """解析失败必须原样返回 —— 审计记录不允许因为格式化而丢失"""
        module = load_formatter_module()
        raw = u'["未闭合'

        self.assertEqual(module.format_default_value(raw), raw)


class TestSignatureFormatter(unittest.TestCase):
    """电子签名必须能在审计界面渲染出来（21 CFR Part 11 §11.50）"""

    def test_signature_from_structured_metadata(self):
        """优先取结构化的 metadata["esignature"]"""
        module = load_formatter_module()
        data = module.extract_signature({
            "esignature": {
                "enabled": True,
                "primary_signer_user_id": "analyst2",
                "meaning": u"批准",
                "reason": u"复核通过",
                "require_countersign": False,
                "auth_backend_id": "pas",
            },
        })

        self.assertEqual(data["signer"], u"analyst2")
        self.assertEqual(data["meaning"], u"批准")
        self.assertFalse(data["require_countersign"])

    def test_signature_falls_back_to_comments_summary(self):
        """结构化字典缺失时（策略关掉了摘要）必须能从 comments 解出来"""
        module = load_formatter_module()
        data = module.extract_signature({
            "comments": (
                u"Electronic signature; first_signer=analyst2; "
                u"second_signer=manager1; execution_user=analyst2; "
                u"countersign_required=yes; transition=verify; "
                u"signature_type=verification; meaning=Approval; "
                u"reason=eee; auth_backend=pas"
            ),
        })

        self.assertEqual(data["signer"], u"analyst2")
        self.assertEqual(data["countersigner"], u"manager1")
        self.assertEqual(data["meaning"], u"Approval")
        self.assertTrue(data["require_countersign"])

    def test_ordinary_comment_is_not_a_signature(self):
        """普通工作流备注不能被误认成签名"""
        module = load_formatter_module()

        self.assertIsNone(module.extract_signature({"comments": u"手工复核"}))
        self.assertIsNone(module.extract_signature({}))

    def test_render_signature_html_is_human_readable(self):
        """渲染结果必须是人类可读的，而不是原始字典"""
        module = load_formatter_module()
        html = module.render_signature_html({
            "signer": u"analyst2",
            "countersigner": u"",
            "meaning": u"批准",
            "reason": u"复核通过",
            "require_countersign": True,
            "auth_backend": u"pas",
        }, timestamp=u"2026-08-26 09:31")

        self.assertIn(u"签名人", html)
        self.assertIn(u"analyst2", html)
        self.assertIn(u"2026-08-26 09:31", html)
        self.assertIn(u"批准", html)
        # 要求双签但复核人还没到位，必须显式提示而不是留空
        self.assertIn(u"待复核", html)

    def test_render_signature_html_is_empty_without_signature(self):
        """无签名的行留空，不要占位符噪音"""
        module = load_formatter_module()

        self.assertEqual(module.render_signature_html(None), u"")

    def test_render_signature_html_escapes_input(self):
        """签名原因是用户输入，必须转义"""
        module = load_formatter_module()
        html = module.render_signature_html({
            "signer": u"analyst2",
            "reason": u'<script>alert("x")</script>',
        })

        self.assertNotIn(u"<script>", html)
        self.assertIn(u"&lt;script&gt;", html)


if __name__ == "__main__":
    unittest.main()
