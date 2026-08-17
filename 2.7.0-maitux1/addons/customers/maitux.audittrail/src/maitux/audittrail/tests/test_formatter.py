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


if __name__ == "__main__":
    unittest.main()
