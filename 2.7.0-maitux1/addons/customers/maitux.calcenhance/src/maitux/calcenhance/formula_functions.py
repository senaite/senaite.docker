# -*- coding: utf-8 -*-

from decimal import Decimal
from decimal import ROUND_HALF_EVEN


def round_half_even(value, precision=0):
    """按“四舍六入五看双”规则舍入并返回 float。

    中文说明：
    - 小于 5 直接舍去
    - 大于 5 直接进位
    - 等于 5 时看保留位前一位，奇进偶舍
    """
    # 中文注释：统一转成字符串再交给 Decimal，避免二进制浮点误差影响 5 的判断。
    decimal_value = Decimal(str(value))
    precision = int(precision)

    # 中文注释：precision=2 -> 0.01；precision=0 -> 1；precision=-1 -> 10。
    quantize_exp = Decimal("1").scaleb(-precision)
    rounded = decimal_value.quantize(quantize_exp, rounding=ROUND_HALF_EVEN)
    return float(rounded)
