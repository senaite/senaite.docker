# -*- coding: utf-8 -*-
"""兼容旧版接口导入，避免 ZODB 旧对象反序列化失败。"""

from maitux.esignature.interfaces import IMedaiSenaiteESignatureLayer

__all__ = ["IMedaiSenaiteESignatureLayer"]
