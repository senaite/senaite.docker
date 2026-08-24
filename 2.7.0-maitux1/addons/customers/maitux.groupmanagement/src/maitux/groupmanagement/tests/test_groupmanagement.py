# -*- coding: utf-8 -*-
"""maitux.groupmanagement 单元测试

轻量 stub 测试（仿 maitux.stock 模式）：不依赖 Plone 运行时，
用最小桩替换外部包后直接加载目标模块验证行为，可在 Python 2/3 下运行：

    python -m unittest maitux.groupmanagement.tests.test_groupmanagement

覆盖：
  - 组管理总览视图：portal_roles 不含 Manager、删除被拦截、请求清洗
  - @@lims-setup 入口：虚拟 tile、图标、计数
  - 模板：不含删除列 / Manager 列，链接全部指向独立视图
"""

import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.abspath(os.path.join(HERE, ".."))

MANAGER_ROLE = "Manager"


class _Logger(object):
    """极简 logger 桩"""
    info = staticmethod(lambda *a, **k: None)
    warn = staticmethod(lambda *a, **k: None)


class _FakeRequest(object):
    def __init__(self, form):
        self.form = form


class _FakePortal(object):
    """模拟 portal 根对象（absolute_url + 属性管理）"""

    def __init__(self, properties=None):
        self._properties = properties or {}

    def absolute_url(self):
        return "http://nohost/plone"

    def getProperty(self, key, default=None):
        return self._properties.get(key, default)

    def hasProperty(self, key):
        return key in self._properties

    def manage_addProperty(self, key, value, ptype):
        self._properties[key] = value

    def manage_delProperties(self, keys):
        for key in keys:
            self._properties.pop(key, None)


def _seed_maitux_config():
    """向 sys.modules 注入 maitux.groupmanagement.config 依赖桩"""
    sys.modules["maitux"] = types.ModuleType("maitux")
    sys.modules["maitux.groupmanagement"] = types.ModuleType(
        "maitux.groupmanagement")
    config = types.ModuleType("maitux.groupmanagement.config")
    config.PROJECTNAME = "maitux.groupmanagement"
    config.INSTALLED_PROPERTY = "maitux_groupmanagement_installed"
    config.BROWSER_LAYER_NAME = "maitux.groupmanagement"
    sys.modules["maitux.groupmanagement.config"] = config


def _load_module(name, relpath):
    """从 add-on 包内按相对路径加载模块（兼容 Python 2/3）"""
    path = os.path.abspath(os.path.join(PKG, relpath))
    if sys.version_info[0] >= 3:
        import importlib.util
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    import imp
    return imp.load_source(name, path)


def _seed_senaite_core():
    """向 sys.modules 注入 senaite.core 依赖桩"""
    sys.modules["senaite"] = types.ModuleType("senaite")
    senaite_core = types.ModuleType("senaite.core")
    senaite_core.logger = _Logger()
    sys.modules["senaite.core"] = senaite_core
    sys.modules["senaite.core.browser"] = types.ModuleType(
        "senaite.core.browser")
    sys.modules["senaite.core.browser.usergroup"] = types.ModuleType(
        "senaite.core.browser.usergroup")
    sys.modules["senaite.core.browser.controlpanel"] = types.ModuleType(
        "senaite.core.browser.controlpanel")


class TestGroupManagementView(unittest.TestCase):
    """browser/groupsoverview.py 行为测试"""

    class StubBase(object):
        """模拟 CMFPlone/senaite.core 的 GroupsOverviewControlPanel"""

        @property
        def portal_roles(self):
            return ["Manager", "LabManager", "LabClerk"]

        def __call__(self):
            return "rendered"

    def setUp(self):
        _seed_senaite_core()
        usergroup = types.ModuleType(
            "senaite.core.browser.usergroup.usergroups_groupsoverview")
        usergroup.GroupsOverviewControlPanel = self.StubBase
        sys.modules[
            "senaite.core.browser.usergroup.usergroups_groupsoverview"
        ] = usergroup
        self.module = _load_module(
            "maitux_groupmanagement_groupsoverview", "browser/groupsoverview.py")

    def _make_view(self, form):
        view = object.__new__(self.module.GroupManagementView)
        view.request = _FakeRequest(form)
        return view

    def test_portal_roles_excludes_manager(self):
        view = self._make_view({})
        roles = view.portal_roles
        self.assertNotIn(MANAGER_ROLE, roles)
        self.assertIn("LabManager", roles)
        self.assertIn("LabClerk", roles)

    def test_strip_delete_removes_delete_keys(self):
        form = {"delete:list": ["Group1"], "delete": "x", "searchstring": "a"}
        self.module.GroupManagementView._strip_delete(form)
        self.assertNotIn("delete:list", form)
        self.assertNotIn("delete", form)
        self.assertIn("searchstring", form)

    def test_strip_manager_removes_manager_from_group_fields(self):
        form = {"group_staff:list": ["Manager", "LabManager"], "other": "x"}
        self.module.GroupManagementView._strip_manager(form)
        self.assertNotIn(MANAGER_ROLE, form["group_staff:list"])
        self.assertIn("LabManager", form["group_staff:list"])

    def test_strip_manager_handles_single_string_value(self):
        form = {"group_staff:list": "Manager"}
        self.module.GroupManagementView._strip_manager(form)
        self.assertEqual([], form["group_staff:list"])

    def test_strip_manager_ignores_unrelated_keys(self):
        form = {"searchstring": "Manager", "foo:list": ["Manager"]}
        self.module.GroupManagementView._strip_manager(form)
        self.assertEqual("Manager", form["searchstring"])
        self.assertEqual(["Manager"], form["foo:list"])

    def test_call_sanitizes_modify_request_and_delegates_to_base(self):
        form = {
            "form.button.Modify": "Save",
            "delete:list": ["Group1"],
            "group_staff:list": ["Manager", "LabManager"],
        }
        view = self._make_view(form)
        result = view()
        self.assertEqual(result, "rendered")
        self.assertNotIn("delete:list", form)
        self.assertNotIn(MANAGER_ROLE, form["group_staff:list"])
        self.assertIn("LabManager", form["group_staff:list"])

    def test_call_does_not_touch_plain_search_requests(self):
        form = {"searchstring": "lab", "form.button.Search": "Search"}
        view = self._make_view(form)
        result = view()
        self.assertEqual(result, "rendered")
        self.assertEqual(form["searchstring"], "lab")
        self.assertIn("form.button.Search", form)

    def test_delete_groups_is_noop(self):
        view = self._make_view({})
        result = view.deleteGroups(["Group1", "Group2"])
        self.assertTrue(result)


class TestSetupView(unittest.TestCase):
    """browser/setupview.py 的 @@lims-setup 入口测试"""

    class StubBase(object):
        """模拟 senaite.core 的 SetupView"""

        def setupitems(self):
            return []

        def get_count(self, obj):
            return 42

        def get_icon_for(self, brain, **kw):
            return "default-icon"

    def setUp(self):
        _seed_senaite_core()
        _seed_maitux_config()
        self.portal = _FakePortal()
        bika_lims = types.ModuleType("bika.lims")
        bika_lims.api = types.ModuleType("bika.lims.api")
        bika_lims.api.get_portal = lambda: self.portal
        sys.modules["bika"] = types.ModuleType("bika")
        sys.modules["bika.lims"] = bika_lims
        sys.modules["bika.lims.api"] = bika_lims.api

        setupview = types.ModuleType(
            "senaite.core.browser.controlpanel.setupview")
        setupview.SetupView = self.StubBase
        sys.modules["senaite.core.browser.controlpanel.setupview"] = setupview

        self.module = _load_module(
            "maitux_groupmanagement_setupview", "browser/setupview.py")

    def test_setupitems_appends_group_management_entry_when_installed(self):
        # 安装标记存在 -> 入口出现
        self.portal._properties["maitux_groupmanagement_installed"] = True
        view = object.__new__(self.module.SetupView)
        items = view.setupitems()
        self.assertEqual(1, len(items))
        entry = items[0]
        self.assertEqual("Group Management", entry.Title)
        self.assertEqual(
            "http://nohost/plone/@@maitux-group-management",
            entry.absolute_url)

    def test_setupitems_empty_when_not_installed(self):
        # 卸载后安装标记被清除 -> 入口消失（浏览器层残留也不显示）
        view = object.__new__(self.module.SetupView)
        items = view.setupitems()
        self.assertEqual([], items)

    def test_get_count_returns_zero_for_entry(self):
        view = object.__new__(self.module.SetupView)
        entry = self.module.SetupEntry("Group Management", "http://x")
        self.assertEqual(0, view.get_count(entry))
        self.assertEqual(42, view.get_count("other"))

    def test_get_icon_for_returns_fa_users_cog_for_entry(self):
        view = object.__new__(self.module.SetupView)
        entry = self.module.SetupEntry("Group Management", "http://x")
        icon = view.get_icon_for(entry)
        self.assertIn("fas fa-users-cog", icon)
        # 其余条目仍然走基类
        self.assertEqual("default-icon", view.get_icon_for("other"))


class TestTemplates(unittest.TestCase):
    """模板中不应再出现删除/Manager 相关元素，链接指向独立视图"""

    TEMPLATES = ("groupsoverview.pt", "groupdetails.pt",
                 "groupmembership.pt")

    def _read(self, name):
        path = os.path.join(PKG, "browser", "templates", name)
        with open(path, "rb") as handle:
            return handle.read().decode("utf-8")

    def test_groupsoverview_template_has_no_delete_column(self):
        tmpl = self._read("groupsoverview.pt")
        self.assertNotIn("delete:list", tmpl)
        self.assertNotIn("listingheader_remove", tmpl)
        # 角色矩阵只应通过 portal_roles 渲染，不允许出现硬编码 Manager 复选框
        self.assertNotIn('value="Manager"', tmpl)
        self.assertNotIn('value="manager"', tmpl)

    def test_groupsoverview_template_uses_standalone_views(self):
        tmpl = self._read("groupsoverview.pt")
        self.assertIn("@@maitux-group-management", tmpl)
        self.assertIn("@@maitux-group-membership", tmpl)
        self.assertIn("@@maitux-group-details", tmpl)
        self.assertIn("@@lims-setup", tmpl)

    def test_groupdetails_template_links_back_to_standalone(self):
        tmpl = self._read("groupdetails.pt")
        self.assertIn("@@maitux-group-details", tmpl)
        self.assertIn("@@maitux-group-management", tmpl)
        self.assertIn("@@maitux-group-membership", tmpl)

    def test_groupmembership_template_links_back_to_standalone(self):
        tmpl = self._read("groupmembership.pt")
        self.assertIn("@@maitux-group-membership", tmpl)
        self.assertIn("@@maitux-group-management", tmpl)
        self.assertIn("@@maitux-group-details", tmpl)

    def test_templates_do_not_reference_old_usergroup_views(self):
        """独立界面不得再链接回旧的 @@usergroup-* 视图"""
        for name in self.TEMPLATES:
            tmpl = self._read(name)
            self.assertNotIn("@@usergroup-", tmpl)


class TestZCML(unittest.TestCase):
    """ZCML 注册的正确性测试"""

    def _read(self, name):
        path = os.path.join(PKG, name)
        with open(path, "rb") as handle:
            return handle.read().decode("utf-8")

    def test_configure_zcml_includes_cmfplone_permissions_before_views(self):
        """browser:page 使用 plone.app.controlpanel.UsersAndGroups 前，
        必须显式引入 CMFPlone 的 permissions.zcml，避免 ZCML 加载顺序
        导致的 ComponentLookupError；且不得重复 <permission> 注册，
        否则与 CMFPlone 的注册参数不一致会触发 ConfigurationConflictError"""
        zcml = self._read("browser/configure.zcml")
        self.assertIn(
            '<include package="Products.CMFPlone" '
            'file="controlpanel/permissions.zcml" />', zcml)
        self.assertNotIn(
            'id="plone.app.controlpanel.UsersAndGroups"', zcml)
        # include 必须位于使用该权限的 browser:page 之前
        inc_pos = zcml.find('file="controlpanel/permissions.zcml"')
        page_pos = zcml.find('name="maitux-group-management"')
        self.assertNotEqual(-1, inc_pos)
        self.assertNotEqual(-1, page_pos)
        self.assertLess(inc_pos, page_pos)

    def test_browser_views_registered_with_expected_permission(self):
        zcml = self._read("browser/configure.zcml")
        # 三个组管理视图使用与 senaite.core 原视图一致的权限
        self.assertEqual(3, zcml.count(
            'permission="plone.app.controlpanel.UsersAndGroups"'))
        # lims-setup 覆盖使用 senaite.core 原视图的权限
        self.assertIn('permission="senaite.core.permissions.ManageBika"', zcml)


class _FakeSkinTool(object):
    """模拟 portal_skins（支持 delSkinLayer / manage_delObjects）"""

    def __init__(self, has_del_skin_layer=True):
        self.deleted_via_del = []
        self.deleted_via_objects = []
        self.ids = ["some-other-layer"]
        self._has_del_skin_layer = has_del_skin_layer

    def delSkinLayer(self, name):
        if not self._has_del_skin_layer:
            # 模拟 Plone 皮肤工具未提供该 API 的场景
            raise AttributeError("delSkinLayer not available")
        self.deleted_via_del.append(name)

    def objectIds(self):
        return list(self.ids)

    def manage_delObjects(self, names):
        for name in names:
            if name in self.ids:
                self.ids.remove(name)
                self.deleted_via_objects.append(name)


class TestSetuphandlers(unittest.TestCase):
    """setuphandlers.py 的安装/卸载行为测试"""

    def setUp(self):
        _seed_senaite_core()
        _seed_maitux_config()

        # Products.CMFPlone.interfaces.INonInstallable
        cmfplone_interfaces = types.ModuleType(
            "Products.CMFPlone.interfaces")
        cmfplone_interfaces.INonInstallable = object
        sys.modules["Products"] = types.ModuleType("Products")
        sys.modules["Products.CMFPlone"] = types.ModuleType(
            "Products.CMFPlone")
        sys.modules["Products.CMFPlone.interfaces"] = cmfplone_interfaces

        # Products.CMFCore.utils.getToolByName
        cmfcore_utils = types.ModuleType("Products.CMFCore.utils")
        cmfcore_utils.getToolByName = lambda context, name: (
            context.skinstool if name == "portal_skins" else None)
        sys.modules["Products.CMFCore"] = types.ModuleType(
            "Products.CMFCore")
        sys.modules["Products.CMFCore.utils"] = cmfcore_utils

        # zope.interface.implementer
        zope_interface = types.ModuleType("zope.interface")
        zope_interface.implementer = lambda *ifaces: (lambda cls: cls)
        sys.modules["zope"] = types.ModuleType("zope")
        sys.modules["zope.interface"] = zope_interface

        self.module = _load_module(
            "maitux_groupmanagement_setuphandlers", "setuphandlers.py")

    def _make_portal(self, has_del_skin_layer=True):
        portal = _FakePortal()
        portal.skinstool = _FakeSkinTool(
            has_del_skin_layer=has_del_skin_layer)
        return portal

    def test_run_install_steps_sets_installed_marker(self):
        portal = self._make_portal()
        self.module.run_install_steps(portal)
        self.assertTrue(portal.getProperty(
            "maitux_groupmanagement_installed", False))

    def test_run_uninstall_steps_clears_marker_and_removes_layer(self):
        portal = self._make_portal()
        portal._properties["maitux_groupmanagement_installed"] = True
        self.module.run_uninstall_steps(portal)
        # 安装标记清除 -> @@lims-setup 入口消失
        self.assertFalse(portal.hasProperty(
            "maitux_groupmanagement_installed"))
        # 浏览器层移除（delSkinLayer 路径）
        self.assertEqual(
            ["maitux.groupmanagement"], portal.skinstool.deleted_via_del)

    def test_remove_browser_layer_falls_back_to_manage_del_objects(self):
        portal = self._make_portal(has_del_skin_layer=False)
        portal.skinstool.ids.append("maitux.groupmanagement")
        self.module._remove_browser_layer(portal)
        self.assertEqual(
            ["maitux.groupmanagement"],
            portal.skinstool.deleted_via_objects)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestGroupManagementView))
    suite.addTest(unittest.makeSuite(TestSetupView))
    suite.addTest(unittest.makeSuite(TestTemplates))
    suite.addTest(unittest.makeSuite(TestZCML))
    suite.addTest(unittest.makeSuite(TestSetuphandlers))
    return suite


if __name__ == "__main__":
    unittest.main()
