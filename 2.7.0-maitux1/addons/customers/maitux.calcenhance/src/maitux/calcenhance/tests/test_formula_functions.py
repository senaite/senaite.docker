# -*- coding: utf-8 -*-

import imp
import os
import unittest


BASE_DIR = os.path.dirname(os.path.dirname(__file__))


def load_module(module_name, file_name):
    """从源码文件直接加载模块，避免触发站点级初始化依赖。"""
    module_path = os.path.join(BASE_DIR, file_name)
    return imp.load_source(module_name, module_path)


class TestFormulaFunctions(unittest.TestCase):
    """验证四舍六入五看双函数及其公式全局变量接入。"""

    def test_round_half_even_uses_bankers_rounding(self):
        # 中文注释：1.225 保留两位时应落在偶数位 1.22，而不是 1.23
        module = load_module("maitux_calcenhance_formula_functions",
                             "formula_functions.py")

        result = module.round_half_even("1.225", 2)

        self.assertEqual(result, 1.22)

    def test_formula_globals_expose_round_half_even(self):
        # 中文注释：公式执行上下文必须暴露 round_half_even，后续公式才能直接调用
        module = load_module("maitux_calcenhance_formula_support",
                             "formula_support.py")

        globals_dict = module.get_additional_formula_globals()

        self.assertIn("round_half_even", globals_dict)
        self.assertEqual(globals_dict["round_half_even"]("1.235", 2), 1.24)
