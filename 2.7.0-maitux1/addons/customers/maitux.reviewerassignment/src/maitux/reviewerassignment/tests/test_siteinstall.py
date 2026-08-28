# -*- coding: utf-8 -*-
"""站点级安装判定测试

siteinstall 是给 for="*" 的进程级 IGuardAdapter 做站点级收口用的：
未安装本 addon 的站点必须判成 False，让 guard 直接放行。
"""

import imp
import os
import unittest


MODULE_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), os.pardir, "siteinstall.py"))
siteinstall = imp.load_source("ra_siteinstall", MODULE_PATH)


class FakeQuickInstaller(object):
    def __init__(self, installed=None, raises=False):
        self.installed = installed or {}
        self.raises = raises
        self.asked = []

    def isProductInstalled(self, name):  # noqa camelCase - 模仿 Plone 工具
        self.asked.append(name)
        if self.raises:
            raise ValueError("boom")
        return self.installed.get(name, False)


class FakeSetupTool(object):
    def __init__(self, versions=None, raises=False):
        self.versions = versions or {}
        self.raises = raises

    def getLastVersionForProfile(self, profile_id):  # noqa camelCase
        if self.raises:
            raise ValueError("boom")
        return self.versions.get(profile_id, "unknown")


class FakeSite(object):
    """只需要能被 getToolByName 取工具、并给出物理路径"""

    def __init__(self, path=("", "Care"), tools=None):
        self.path = path
        self.tools = tools or {}

    def getPhysicalPath(self):  # noqa camelCase
        return self.path


def fake_get_tool_by_name(site, name, default=None):
    return site.tools.get(name, default)


class TestProfileVersionPredicate(unittest.TestCase):
    """portal_setup 的返回值到「已安装」的映射"""

    def test_unknown_string_is_not_installed(self):
        """没装过的 profile，portal_setup 返回字符串 unknown"""
        self.assertFalse(siteinstall.is_profile_version_installed("unknown"))

    def test_unknown_tuple_is_not_installed(self):
        """元组形式的 unknown 同样算没装"""
        self.assertFalse(
            siteinstall.is_profile_version_installed(("unknown", )))

    def test_empty_values_are_not_installed(self):
        """空值一律算没装"""
        self.assertFalse(siteinstall.is_profile_version_installed(None))
        self.assertFalse(siteinstall.is_profile_version_installed(""))
        self.assertFalse(siteinstall.is_profile_version_installed(()))
        self.assertFalse(siteinstall.is_profile_version_installed(("", )))

    def test_version_tuple_is_installed(self):
        """装过则返回版本元组"""
        self.assertTrue(
            siteinstall.is_profile_version_installed((u"1", u"0", u"0")))

    def test_version_string_is_installed(self):
        """字符串版本号也算装了"""
        self.assertTrue(siteinstall.is_profile_version_installed("1.0.0"))


class TestQuerySiteInstalled(unittest.TestCase):
    """站点查询：先 quickinstaller，取不到再退回 portal_setup"""

    def setUp(self):
        self._original = siteinstall.getToolByName
        siteinstall.getToolByName = fake_get_tool_by_name

    def tearDown(self):
        siteinstall.getToolByName = self._original

    def test_no_site_is_not_installed(self):
        """拿不到站点时按未安装处理"""
        self.assertFalse(siteinstall.query_site_installed(None))

    def test_quickinstaller_says_installed(self):
        """已安装站点"""
        qi = FakeQuickInstaller({"maitux.reviewerassignment": True})
        site = FakeSite(tools={"portal_quickinstaller": qi})
        self.assertTrue(siteinstall.query_site_installed(site))
        self.assertEqual(qi.asked, ["maitux.reviewerassignment"])

    def test_quickinstaller_says_not_installed(self):
        """未安装站点必须判 False，这是放行的依据"""
        qi = FakeQuickInstaller({"maitux.reviewerassignment": False})
        site = FakeSite(tools={"portal_quickinstaller": qi})
        self.assertFalse(siteinstall.query_site_installed(site))

    def test_falls_back_to_portal_setup_when_no_quickinstaller(self):
        """没有 quickinstaller 时退回 portal_setup 的 profile 版本"""
        setup_tool = FakeSetupTool(
            {"maitux.reviewerassignment:default": (u"1", u"0", u"0")})
        site = FakeSite(tools={"portal_setup": setup_tool})
        self.assertTrue(siteinstall.query_site_installed(site))

    def test_falls_back_to_portal_setup_when_quickinstaller_raises(self):
        """quickinstaller 抛错时也退回 portal_setup"""
        setup_tool = FakeSetupTool(
            {"maitux.reviewerassignment:default": (u"1", u"0", u"0")})
        site = FakeSite(tools={
            "portal_quickinstaller": FakeQuickInstaller(raises=True),
            "portal_setup": setup_tool,
        })
        self.assertTrue(siteinstall.query_site_installed(site))

    def test_portal_setup_unknown_is_not_installed(self):
        """profile 从没导入过的站点判 False"""
        site = FakeSite(tools={"portal_setup": FakeSetupTool()})
        self.assertFalse(siteinstall.query_site_installed(site))

    def test_no_tool_at_all_is_not_installed(self):
        """两个工具都取不到时按未安装处理，不能抛错"""
        self.assertFalse(siteinstall.query_site_installed(FakeSite()))

    def test_portal_setup_raises_is_not_installed(self):
        """portal_setup 抛错时按未安装处理，不能把异常带进 guard"""
        site = FakeSite(tools={"portal_setup": FakeSetupTool(raises=True)})
        self.assertFalse(siteinstall.query_site_installed(site))


class TestCurrentSiteCaching(unittest.TestCase):
    """判定结果按请求缓存：guard 在列表视图里一个请求会被调上百次"""

    def setUp(self):
        self._get_tool = siteinstall.getToolByName
        self._get_site = siteinstall.getSite
        siteinstall.getToolByName = fake_get_tool_by_name

    def tearDown(self):
        siteinstall.getToolByName = self._get_tool
        siteinstall.getSite = self._get_site

    def test_no_site_returns_false(self):
        """没有当前站点（纯 Zope 根上下文）时放行"""
        siteinstall.getSite = lambda: None
        self.assertFalse(siteinstall.is_installed_in_current_site())

    def test_result_is_cached_on_the_request(self):
        """同一请求内只查一次站点"""

        class FakeRequest(dict):
            def set(self, key, value):
                self[key] = value

        qi = FakeQuickInstaller({"maitux.reviewerassignment": True})
        site = FakeSite(tools={"portal_quickinstaller": qi})
        site.REQUEST = FakeRequest()
        siteinstall.getSite = lambda: site

        self.assertTrue(siteinstall.is_installed_in_current_site())
        self.assertTrue(siteinstall.is_installed_in_current_site())
        self.assertEqual(len(qi.asked), 1)

    def test_works_without_request(self):
        """脚本/定时任务里没有 request，不缓存但也不能抛错"""
        qi = FakeQuickInstaller({"maitux.reviewerassignment": True})
        site = FakeSite(tools={"portal_quickinstaller": qi})
        siteinstall.getSite = lambda: site
        self.assertTrue(siteinstall.is_installed_in_current_site())
        self.assertTrue(siteinstall.is_installed_in_current_site())
        self.assertEqual(len(qi.asked), 2)

    def test_cache_key_is_per_site(self):
        """key 带站点路径，避免同一请求跨站点串味"""

        class FakeRequest(dict):
            def set(self, key, value):
                self[key] = value

        request = FakeRequest()
        installed_site = FakeSite(
            path=("", "Care"),
            tools={"portal_quickinstaller": FakeQuickInstaller(
                {"maitux.reviewerassignment": True})})
        installed_site.REQUEST = request
        other_site = FakeSite(
            path=("", "MaiLIMS"),
            tools={"portal_quickinstaller": FakeQuickInstaller(
                {"maitux.reviewerassignment": False})})
        other_site.REQUEST = request

        siteinstall.getSite = lambda: installed_site
        self.assertTrue(siteinstall.is_installed_in_current_site())
        siteinstall.getSite = lambda: other_site
        self.assertFalse(siteinstall.is_installed_in_current_site())


if __name__ == "__main__":
    unittest.main()
