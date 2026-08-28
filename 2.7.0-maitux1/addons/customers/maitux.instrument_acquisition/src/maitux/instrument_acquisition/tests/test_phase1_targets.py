# -*- coding: utf-8 -*-
"""第一阶段静态目标位定义测试

纯单元测试：不依赖 Zope 运行环境。
为避免触发包级 __init__（引入 bika.lims 等 Zope 依赖），
直接按文件路径加载 phase1_targets.py。
"""

import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "..", "services", "phase1_targets.py")


def _load_source(name, path):
    """按文件路径加载模块（py2 用 imp；py3.12+ 用 importlib.util）"""
    try:
        import imp
        return imp.load_source(name, path)
    except ImportError:
        import importlib.util
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


_targets = _load_source("maitux_phase1_targets_test", _MODULE_PATH)


class Phase1TargetsTest(unittest.TestCase):
    """校验第一阶段静态目标位定义格式与 target_key 抽象"""

    def test_keywords_present(self):
        self.assertIn("T_name", _targets.PHASE1_KEYWORDS)
        self.assertIn("T_weight", _targets.PHASE1_KEYWORDS)

    def test_target_definitions_format(self):
        definitions = _targets.get_target_definitions()
        self.assertTrue(definitions)
        for definition in definitions:
            self.assertIn("target_key", definition)
            self.assertIn("interim_keyword", definition)
            self.assertIn("display_title", definition)
            self.assertIn("allow_multi_assign", definition)
            self.assertIn("sort_order", definition)
            # 第一阶段目标位关键字必须是写死集合中的一员
            self.assertIn(definition["interim_keyword"], _targets.PHASE1_KEYWORDS)
            self.assertEqual(definition["target_key"], definition["interim_keyword"])

    def test_target_definitions_unique(self):
        definitions = _targets.get_target_definitions()
        keys = [d["target_key"] for d in definitions]
        self.assertEqual(len(keys), len(set(keys)))

    def test_get_target_definition(self):
        definition = _targets.get_target_definition("T_weight")
        self.assertIsNotNone(definition)
        self.assertEqual(definition["display_title"], u"重量")
        self.assertIsNone(_targets.get_target_definition("not-exists"))

    def test_make_and_parse_target_key(self):
        target_key = _targets.make_target_key("uid-123", "T_weight")
        analysis_uid, keyword = _targets.parse_target_key(target_key)
        self.assertEqual(analysis_uid, "uid-123")
        self.assertEqual(keyword, "T_weight")

    def test_parse_target_key_invalid(self):
        self.assertEqual(_targets.parse_target_key(""), (None, None))
        self.assertEqual(_targets.parse_target_key("no-separator"), (None, None))
        self.assertEqual(_targets.parse_target_key("uid:"), (None, None))
        self.assertEqual(_targets.parse_target_key(":kw"), (None, None))

    def test_readonly_keywords(self):
        keywords = _targets.get_readonly_keywords()
        self.assertIn("T_name", keywords)
        self.assertIn("T_weight", keywords)

    def test_token_constant(self):
        self.assertTrue(_targets.PHASE1_INGEST_TOKEN)

    def test_annotation_keys(self):
        self.assertTrue(_targets.PHASE1_ANNOTATION_KEY)
        self.assertTrue(_targets.PHASE1_SESSION_INDEX_KEY)


if __name__ == "__main__":
    unittest.main()
