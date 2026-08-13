# -*- coding: utf-8 -*-
"""兼容旧版 medai.senaite 命名空间。"""

try:
    __import__("pkg_resources").declare_namespace(__name__)
except ImportError:
    from pkgutil import extend_path

    __path__ = extend_path(__path__, __name__)
