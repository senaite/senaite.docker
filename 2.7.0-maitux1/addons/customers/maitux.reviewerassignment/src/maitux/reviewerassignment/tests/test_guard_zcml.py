# -*- coding: utf-8 -*-
"""Guard ZCML 注册测试"""

import os
import unittest
from xml.etree import ElementTree


GUARDS_ZCML = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, "guards", "configure.zcml"))


class TestGuardZCML(unittest.TestCase):
    """避免再次注册匿名 IGuardAdapter 造成 ZCML 冲突"""

    def test_reviewer_guard_adapter_must_be_named(self):
        """审核分配 guard 必须使用具名 adapter"""
        tree = ElementTree.parse(GUARDS_ZCML)
        root = tree.getroot()
        adapter = root.find("{http://namespaces.zope.org/zope}adapter")
        self.assertIsNotNone(adapter)
        self.assertTrue(
            adapter.get("name"),
            "maitux.reviewerassignment 的 IGuardAdapter 必须声明 name，"
            "否则会与其他匿名 guard adapter 产生 ZCML 冲突")
