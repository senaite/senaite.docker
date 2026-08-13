# -*- coding: utf-8 -*-
import importlib.util
import os
import sys
import types
import unittest


EXPECTED_TITLE = u"Stockinventory"


def load_setuphandlers_module():
    """加载 setuphandlers 模块，并用最小桩替换外部依赖。"""
    api_module = types.SimpleNamespace(
        get_tool=lambda name: None,
    )

    sys.modules["bika"] = types.ModuleType("bika")
    sys.modules["bika.lims"] = types.ModuleType("bika.lims")
    sys.modules["bika.lims"].api = api_module
    sys.modules["bika.lims.api"] = api_module

    plone_api_module = types.ModuleType("plone.api")
    plone_module = types.ModuleType("plone")
    plone_module.api = plone_api_module
    sys.modules["plone"] = plone_module
    sys.modules["plone.api"] = plone_api_module

    products_module = types.ModuleType("Products")
    cmfplone_module = types.ModuleType("Products.CMFPlone")
    interfaces_module = types.ModuleType("Products.CMFPlone.interfaces")
    interfaces_module.INonInstallable = object
    sys.modules["Products"] = products_module
    sys.modules["Products.CMFPlone"] = cmfplone_module
    sys.modules["Products.CMFPlone.interfaces"] = interfaces_module

    senaite_core_module = types.ModuleType("senaite.core")
    senaite_core_module.logger = types.SimpleNamespace(info=lambda *args, **kwargs: None)
    sys.modules["senaite"] = types.ModuleType("senaite")
    sys.modules["senaite.core"] = senaite_core_module

    interface_module = types.ModuleType("zope.interface")
    interface_module.implementer = lambda *ifaces: (lambda cls: cls)
    sys.modules["zope"] = types.ModuleType("zope")
    sys.modules["zope.interface"] = interface_module

    maitux_module = types.ModuleType("maitux")
    stock_package = types.ModuleType("maitux.stock")
    config_module = types.ModuleType("maitux.stock.config")
    config_module.PROJECTNAME = "maitux.stock"
    expiry_module = types.ModuleType("maitux.stock.stockbatchexpiry")
    expiry_module.REVIEW_STATE_ACTIVE = u"active"
    expiry_module.REVIEW_STATE_DESTROYED = u"destroyed"
    expiry_module.expire_batch = lambda *args, **kwargs: False
    expiry_module.is_due_for_expiry = lambda *args, **kwargs: False
    expiry_module.set_status_value = lambda *args, **kwargs: False
    sys.modules["maitux"] = maitux_module
    sys.modules["maitux.stock"] = stock_package
    sys.modules["maitux.stock.config"] = config_module
    sys.modules["maitux.stock.stockbatchexpiry"] = expiry_module

    file_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "setuphandlers.py"))
    spec = importlib.util.spec_from_file_location("test_setuphandlers_module", file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_stockmanagerfix_module():
    """加载 stockmanagerfix 模块，并用最小桩替换外部依赖。"""
    browser_module = types.ModuleType("Products.Five.browser")
    browser_module.BrowserView = object
    sys.modules["Products"] = types.ModuleType("Products")
    sys.modules["Products.Five"] = types.ModuleType("Products.Five")
    sys.modules["Products.Five.browser"] = browser_module

    api_module = types.SimpleNamespace(
        get_portal_type=lambda obj: getattr(obj, "portal_type", ""),
        get_url=lambda obj: "/stockmanager",
    )
    sys.modules["bika"] = types.ModuleType("bika")
    sys.modules["bika.lims"] = types.ModuleType("bika.lims")
    sys.modules["bika.lims"].api = api_module
    sys.modules["bika.lims.api"] = api_module
    sys.modules["bika.lims"].senaiteMessageFactory = lambda value: value

    file_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "browser", "stockmanagerfix.py"))
    spec = importlib.util.spec_from_file_location("test_stockmanagerfix_module", file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DummyResponse(object):
    def redirect(self, url):
        return url


class DummyContext(object):
    portal_type = "StockManager"

    def __init__(self):
        self._title = u"Wrong title"
        self.plone_utils = types.SimpleNamespace(
            addPortalMessage=lambda *args, **kwargs: None)

    def Title(self):
        return self._title

    def setTitle(self, value):
        self._title = value

    def reindexObject(self):
        return None

    def objectIds(self):
        return []

    def get(self, key):
        return None


class TestStockManagerTitle(unittest.TestCase):

    def test_setuphandlers_title_constant_is_correct(self):
        """安装脚本中的 StockManager 标题不应再保留旧拼写。"""
        module = load_setuphandlers_module()
        self.assertEqual(module.STOCK_MANAGER_TITLE, EXPECTED_TITLE)

    def test_stockmanager_fix_view_uses_correct_title(self):
        """修复视图应把 StockManager 标题统一修正为正确拼写。"""
        module = load_stockmanagerfix_module()
        context = DummyContext()
        request = types.SimpleNamespace(response=DummyResponse())
        view = module.StockStructureFixView()
        view.context = context
        view.request = request

        view()

        self.assertEqual(context.Title(), EXPECTED_TITLE)

    def test_stockmanager_xml_title_is_correct(self):
        """类型定义中的默认标题不应包含 Stcok 拼写错误。"""
        file_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "profiles", "default", "types", "StockManager.xml"))
        with open(file_path, "r") as handle:
            xml_text = handle.read()

        self.assertIn(EXPECTED_TITLE, xml_text)
        self.assertNotIn("Stcokinventory", xml_text)
