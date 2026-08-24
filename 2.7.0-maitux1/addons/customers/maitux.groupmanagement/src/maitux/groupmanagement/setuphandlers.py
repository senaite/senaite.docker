# -*- coding: utf-8 -*-
"""安装/卸载处理器

本 add-on 不创建任何内容类型或侧边栏条目，仅注册浏览器视图
（独立组管理 + @@lims-setup 入口覆盖）。安装/卸载时需要维护：

  1. 安装标记（portal property）
     浏览器层在卸载时可能残留（依赖 plone.browserlayer 行为），
     @@lims-setup 的入口渲染会检查该标记，保证卸载后 UI 立即消失。

  2. 浏览器层移除
     尽力从 portal_skins 移除本 add-on 的浏览器层，使视图覆盖
     在卸载后整体失效（独立组管理页面不可再访问）。
"""

from Products.CMFCore.utils import getToolByName
from Products.CMFPlone.interfaces import INonInstallable
from senaite.core import logger
from zope.interface import implementer

from maitux.groupmanagement.config import BROWSER_LAYER_NAME
from maitux.groupmanagement.config import INSTALLED_PROPERTY
from maitux.groupmanagement.config import PROJECTNAME


@implementer(INonInstallable)
class HiddenProfiles(object):
    """隐藏卸载 Profile，避免 Add-ons 面板重复显示。"""

    def getNonInstallableProfiles(self):  # noqa camelCase
        return [
            "%s:uninstall" % PROJECTNAME,
        ]

    def getNonInstallableProducts(self):  # noqa camelCase
        return []


def setup_handler(context):
    """标准插件安装入口。"""
    install_file = "%s.txt" % PROJECTNAME
    if context.readDataFile(install_file) is None:
        return

    logger.info("maitux.groupmanagement setup handler [BEGIN]")
    portal = context.getSite()
    run_install_steps(portal)
    logger.info("maitux.groupmanagement setup handler [DONE]")


def run_install_steps(portal):
    """按标准插件方式编排安装步骤。"""
    _set_installed_marker(portal, True)


def uninstall_handler(context):
    """标准插件卸载入口。"""
    uninstall_file = "%s-uninstall.txt" % PROJECTNAME
    if context.readDataFile(uninstall_file) is None:
        return

    logger.info("maitux.groupmanagement uninstall handler [BEGIN]")
    portal = context.getSite()
    run_uninstall_steps(portal)
    logger.info("maitux.groupmanagement uninstall handler [DONE]")


def run_uninstall_steps(portal):
    """编排卸载步骤。"""
    # 1. 清除安装标记 -> @@lims-setup 入口立即消失
    _set_installed_marker(portal, False)
    # 2. 移除浏览器层 -> 视图覆盖整体失效（独立组管理页面不可再访问）
    _remove_browser_layer(portal)


def _set_installed_marker(portal, installed):
    """写入/清除安装标记（portal property）"""
    try:
        if installed:
            if not portal.hasProperty(INSTALLED_PROPERTY):
                portal.manage_addProperty(
                    INSTALLED_PROPERTY, True, "boolean")
        else:
            if portal.hasProperty(INSTALLED_PROPERTY):
                portal.manage_delProperties([INSTALLED_PROPERTY])
    except Exception as exc:  # noqa: B902
        logger.warn(
            "maitux.groupmanagement: could not %s installed marker: %s"
            % ("set" if installed else "remove", exc))


def _remove_browser_layer(portal):
    """尽力移除浏览器层，使 layer 上的视图注册不再命中请求"""
    try:
        skinstool = getToolByName(portal, "portal_skins")
    except Exception as exc:  # noqa: B902
        logger.warn(
            "maitux.groupmanagement: could not get portal_skins: %s" % exc)
        return

    layer_id = BROWSER_LAYER_NAME

    # 首选 plone.browserlayer 约定的皮肤工具 API（Plone 5）
    remove = getattr(skinstool, "delSkinLayer", None)
    if callable(remove):
        try:
            remove(layer_id)
            logger.info(
                "maitux.groupmanagement: removed browser layer '%s' "
                "via delSkinLayer" % layer_id)
            return
        except Exception as exc:  # noqa: B902
            logger.warn(
                "maitux.groupmanagement: delSkinLayer failed: %s" % exc)

    # 兜底：直接删除 portal_skins 中同名的 layer 对象
    try:
        if layer_id in skinstool.objectIds():
            skinstool.manage_delObjects([layer_id])
            logger.info(
                "maitux.groupmanagement: removed browser layer '%s' "
                "via manage_delObjects" % layer_id)
    except Exception as exc:  # noqa: B902
        logger.warn(
            "maitux.groupmanagement: manage_delObjects failed: %s" % exc)
