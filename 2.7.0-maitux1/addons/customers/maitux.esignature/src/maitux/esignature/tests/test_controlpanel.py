# -*- coding: utf-8 -*-
import importlib.util
import io
import os
import sys
import types
import unittest


class DummyResponse(object):
    def __init__(self):
        self.redirected_to = None

    def redirect(self, url):
        self.redirected_to = url
        return url


class DummyRequest(dict):
    def __init__(self, data=None):
        super(DummyRequest, self).__init__(data or {})
        self.response = DummyResponse()

    def get(self, key, default=None):
        return super(DummyRequest, self).get(key, default)


class DummyRegistryRecord(object):
    def __init__(self, field_name, value):
        self.value = value
        self.field = type(field_name, (), {})()


class DummyRegistry(object):
    def __init__(self):
        self.records = {}
        self.registered = False

    def registerInterface(self, interface, prefix=""):
        self.registered = True


def load_controlpanel_module(registry):
    """加载 controlpanel 模块，并替换外部依赖。"""
    api_module = types.SimpleNamespace(
        get_portal=lambda: types.SimpleNamespace(
            plone_utils=types.SimpleNamespace(addPortalMessage=lambda message, level="info": None)
        ),
        get_url=lambda context: "/portal",
        get_tool=lambda name: None,
    )

    sys.modules["bika"] = types.ModuleType("bika")
    sys.modules["bika.lims"] = types.ModuleType("bika.lims")
    sys.modules["bika.lims"].api = api_module
    sys.modules["bika.lims.api"] = api_module

    registry_interfaces = types.ModuleType("plone.registry.interfaces")
    registry_interfaces.IRegistry = object
    sys.modules["plone"] = types.ModuleType("plone")
    sys.modules["plone.registry"] = types.ModuleType("plone.registry")
    sys.modules["plone.registry.interfaces"] = registry_interfaces

    browser_module = types.ModuleType("Products.Five.browser")
    browser_module.BrowserView = object
    sys.modules["Products"] = types.ModuleType("Products")
    sys.modules["Products.Five"] = types.ModuleType("Products.Five")
    sys.modules["Products.Five.browser"] = browser_module

    pt_module = types.ModuleType("Products.Five.browser.pagetemplatefile")
    pt_module.ViewPageTemplateFile = lambda path: path
    sys.modules["Products.Five.browser.pagetemplatefile"] = pt_module

    component_module = types.ModuleType("zope.component")
    component_module.getUtility = lambda iface: registry
    # Registered re-auth providers. The dropdown is built from whatever is
    # registered, so the stub returns the local one only -- exactly what a
    # site without an SSO add-on sees.
    component_module.getUtilitiesFor = lambda iface: [
        ("pas", types.SimpleNamespace(
            backend_id="pas", title=u"Local accounts (Plone PAS)")),
    ]
    sys.modules["zope"] = types.ModuleType("zope")
    sys.modules["zope.component"] = component_module

    interface_module = types.ModuleType("maitux.esignature.interfaces")
    interface_module.IESignatureControlPanelSettings = object
    interface_module.IReAuthenticationProvider = object
    sys.modules["maitux"] = types.ModuleType("maitux")
    sys.modules["maitux.esignature"] = types.ModuleType("maitux.esignature")
    sys.modules["maitux.esignature.interfaces"] = interface_module

    rules_module = types.ModuleType("maitux.esignature.services.rules")
    rules_module.build_legacy_rule = lambda settings: {
        "portal_type": settings.get("pilot_portal_type", ""),
        "workflow_id": settings.get("workflow_id", ""),
        "transition_id": settings.get("pilot_transition", ""),
        "signature_required": True,
        "require_countersign": False,
        "meaning_required": settings.get("meaning_required", True),
        "reason_required": settings.get("reason_required", True),
    }
    rules_module.DEFAULT_MEANINGS = {u"verify": u"Approval"}
    rules_module.DEFAULT_MEANING_VOCABULARY = [u"Approval", u"Review"]
    rules_module.parse_meaning_vocabulary = lambda raw: (
        [l.strip() for l in (raw or u"").splitlines() if l.strip()]
        or list(rules_module.DEFAULT_MEANING_VOCABULARY))
    rules_module.dumps_meaning_vocabulary = (
        lambda items: u"\n".join(items or []))
    rules_module.default_meaning_for = lambda tid: (
        rules_module.DEFAULT_MEANINGS.get(tid, u""))
    rules_module.dumps_policy_rules = lambda rules: u"[]"
    rules_module.loads_policy_rules = lambda text, legacy_rule=None: []
    sys.modules["maitux.esignature.services"] = types.ModuleType("maitux.esignature.services")
    sys.modules["maitux.esignature.services.rules"] = rules_module

    file_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "browser", "controlpanel.py"))
    spec = importlib.util.spec_from_file_location("test_controlpanel_module", file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestESignatureControlPanel(unittest.TestCase):

    def test_template_hides_fixed_base_settings(self):
        """设置页不再显示已固定的基础参数。"""
        template_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "browser", "templates", "controlpanel.pt"))
        # encoding is explicit on purpose: without it Python 3 on Windows
        # defaults to GBK and cannot read these UTF-8 sources.
        with io.open(template_path, "r", encoding="utf-8") as handle:
            content = handle.read()

        self.assertNotIn("Show signature summary in Audit Log", content)
        self.assertNotIn("Default signature type", content)
        self.assertNotIn("Default TTL (seconds)", content)
        self.assertNotIn('name="auditlog_summary_enabled"', content)
        self.assertNotIn('name="signature_type"', content)
        self.assertNotIn('name="verified_context_ttl_seconds"', content)

    def test_handle_save_forces_hidden_fixed_settings(self):
        """隐藏字段后保存时仍应写入固定配置值。"""
        registry = DummyRegistry()
        registry.records["maitux.esignature.enabled"] = DummyRegistryRecord("Bool", True)
        registry.records["maitux.esignature.auditlog_summary_enabled"] = DummyRegistryRecord("Bool", False)
        registry.records["maitux.esignature.verified_context_ttl_seconds"] = DummyRegistryRecord("Int", 600)
        registry.records["maitux.esignature.signature_type"] = DummyRegistryRecord("TextLine", u"custom")
        registry.records["maitux.esignature.policy_rules_json"] = DummyRegistryRecord("Text", u"[]")
        registry.records["maitux.esignature.meaning_vocabulary"] = DummyRegistryRecord("Text", u"")
        registry.records["maitux.esignature.auth_backend"] = DummyRegistryRecord("TextLine", u"pas")

        module = load_controlpanel_module(registry)
        view = module.ESignatureControlPanelView()
        view.context = object()
        view.request = DummyRequest({
            "form.save": "1",
            "enabled": "1",
            "rules_payload": "[]",
        })

        view.handle_save()

        self.assertTrue(
            registry.records["maitux.esignature.auditlog_summary_enabled"].value
        )
        self.assertEqual(
            registry.records["maitux.esignature.verified_context_ttl_seconds"].value,
            300
        )
        self.assertEqual(
            registry.records["maitux.esignature.signature_type"].value,
            u"verification"
        )


if __name__ == "__main__":
    unittest.main()
