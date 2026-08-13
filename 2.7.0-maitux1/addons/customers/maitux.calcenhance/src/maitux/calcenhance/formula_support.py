# -*- coding: utf-8 -*-

import imp
import os


def _load_round_half_even():
    """优先走正式包导入，测试环境回退为按文件加载。"""
    try:
        from maitux.calcenhance.formula_functions import round_half_even
        return round_half_even
    except ImportError:
        module_path = os.path.join(os.path.dirname(__file__),
                                   "formula_functions.py")
        module = imp.load_source(
            "maitux_calcenhance_formula_functions_runtime",
            module_path)
        return module.round_half_even


def get_additional_formula_globals():
    """返回附加到公式执行环境中的公共函数。"""
    return {
        "round_half_even": _load_round_half_even(),
    }
