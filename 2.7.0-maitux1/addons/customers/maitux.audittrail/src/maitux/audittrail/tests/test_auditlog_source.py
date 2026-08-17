# -*- coding: utf-8 -*-
"""审计追踪源码回归测试"""

import os
import unittest


PACKAGE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
CONFIGURE_ZCML = os.path.join(PACKAGE_DIR, "browser", "configure.zcml")
PACKAGE_CONFIGURE_ZCML = os.path.join(PACKAGE_DIR, "configure.zcml")
INTERFACES_SOURCE = os.path.join(PACKAGE_DIR, "interfaces.py")
VIEW_SOURCE = os.path.join(PACKAGE_DIR, "browser", "auditlog.py")
TEMPLATE_SOURCE = os.path.join(
    PACKAGE_DIR, "browser", "templates", "auditlog_diff.pt")
SETUPHANDLERS_SOURCE = os.path.join(PACKAGE_DIR, "setuphandlers.py")
DEFAULT_MARKER = os.path.join(
    PACKAGE_DIR, "profiles", "default", "maitux.audittrail.txt")
UNINSTALL_METADATA = os.path.join(
    PACKAGE_DIR, "profiles", "uninstall", "metadata.xml")
UNINSTALL_MARKER = os.path.join(
    PACKAGE_DIR, "profiles", "uninstall", "maitux.audittrail-uninstall.txt")


class TestAuditLogSource(unittest.TestCase):
    """确保审计追踪页已由 add-on 接管并增强 Interim Fields 展示"""

    def test_browser_layer_extends_senaite_core_layer(self):
        """浏览器层必须继承 ISenaiteCore 和 IBikaLIMS

        core 的 @@auditlog 绑定在 IBikaLIMS 层（bika.lims），
        若只继承 ISenaiteCore 会因无继承关系而无法覆盖原生视图。
        """
        with open(INTERFACES_SOURCE, "r") as handle:
            source = handle.read()

        self.assertIn("from senaite.core.interfaces import ISenaiteCore", source)
        self.assertIn("from bika.lims.interfaces import IBikaLIMS", source)
        self.assertIn("class IAuditTrailLayer(ISenaiteCore, IBikaLIMS):", source)

    def test_browser_zcml_overrides_auditlog_view(self):
        """add-on 需要覆盖 @@auditlog 视图"""
        with open(CONFIGURE_ZCML, "r") as handle:
            source = handle.read()

        self.assertIn('name="auditlog"', source)
        self.assertIn(
            'class="maitux.audittrail.browser.auditlog.AuditLogView"', source)
        self.assertIn(
            'layer="maitux.audittrail.interfaces.IAuditTrailLayer"', source)

    def test_view_uses_raw_diff_and_special_interim_renderer(self):
        """视图需要拿到原始 diff，才能把 InterimFields 渲染成可读结构"""
        with open(VIEW_SOURCE, "r") as handle:
            source = handle.read()

        self.assertIn("compare_snapshots(snapshot, prev_snapshot, raw=True)", source)
        self.assertIn("def is_interim_fields(self, field, value):", source)
        self.assertIn("render_interim_fields_html", source)
        self.assertIn("interim_fields", source)

    def test_template_contains_structured_interim_layout(self):
        """模板要区分普通字段和 InterimFields 的结构化展示"""
        with open(TEMPLATE_SOURCE, "r") as handle:
            source = handle.read()

        self.assertIn("row/is_interim_fields", source)
        self.assertIn("structure d/before_html", source)
        self.assertIn("structure d/after_html", source)

    def test_package_configure_registers_uninstall_profile(self):
        """包级配置要补齐标准卸载 profile 和 importStep"""
        with open(PACKAGE_CONFIGURE_ZCML, "r") as handle:
            source = handle.read()

        self.assertIn('factory=".setuphandlers.HiddenProfiles"', source)
        self.assertIn('name="uninstall"', source)
        self.assertIn('directory="profiles/uninstall"', source)
        self.assertIn(
            'handler="maitux.audittrail.setuphandlers.setup_handler"', source)
        self.assertIn(
            'handler="maitux.audittrail.setuphandlers.uninstall_handler"', source)

    def test_setuphandlers_contains_standard_install_uninstall_entrypoints(self):
        """安装和卸载流程要和其他 add-on 一样走标准 handler"""
        with open(SETUPHANDLERS_SOURCE, "r") as handle:
            source = handle.read()

        self.assertIn("PROJECTNAME = \"maitux.audittrail\"", source)
        self.assertIn("@implementer(INonInstallable)", source)
        self.assertIn("class HiddenProfiles(object):", source)
        self.assertIn("def setup_handler(context):", source)
        self.assertIn("def uninstall_handler(context):", source)
        self.assertIn("def import_various(context):", source)

    def test_uninstall_profile_files_exist(self):
        """安装和卸载目录都要有标准标记文件"""
        self.assertTrue(os.path.isfile(DEFAULT_MARKER))
        self.assertTrue(os.path.isfile(UNINSTALL_METADATA))
        self.assertTrue(os.path.isfile(UNINSTALL_MARKER))


if __name__ == "__main__":
    unittest.main()
