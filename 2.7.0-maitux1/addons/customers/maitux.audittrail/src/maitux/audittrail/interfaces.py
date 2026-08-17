# -*- coding: utf-8 -*-
"""模块级接口定义"""

from bika.lims.interfaces import IBikaLIMS
from senaite.core.interfaces import ISenaiteCore


class IAuditTrailLayer(ISenaiteCore, IBikaLIMS):
    """审计追踪可读性增强浏览器层

    同时继承 ISenaiteCore 与 IBikaLIMS：
    core 的 @@auditlog 视图绑定在 IBikaLIMS 层上，只有我们的层
    也继承 IBikaLIMS 才能压过原生视图，让覆盖真正生效。
    """
