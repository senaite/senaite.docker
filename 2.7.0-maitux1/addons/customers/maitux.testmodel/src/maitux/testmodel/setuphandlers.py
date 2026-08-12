# -*- coding: utf-8 -*-
"""标准插件安装/卸载处理器。"""

from bika.lims import api
from plone import api as ploneapi
from Products.CMFPlone.interfaces import INonInstallable
from senaite.core import logger
from zope.interface import implementer

from maitux.testmodel.config import PROJECTNAME

ROOT_ID = "testmodelroot"
ROOT_TYPE = "TestmodelContainer"
ROOT_TITLE = "Testmodel Management"


@implementer(INonInstallable)
class HiddenProfiles(object):
    """隐藏卸载 Profile，保持 Add-ons 面板整洁。"""

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

    logger.info("Maitux.Testmodel setup handler [BEGIN]")
    portal = context.getSite()
    run_install_steps(portal)
    logger.info("Maitux.Testmodel setup handler [DONE]")


def run_install_steps(portal):
    """按标准插件模式编排安装步骤。"""
    setup_type_constraints()
    root_container = setup_site_structure(portal)
    setup_permissions(root_container)
    setup_sidebar()


def setup_type_constraints():
    """先检查再修改类型约束。"""
    logger.info("*** Setup Testmodel Type Constraints ***")
    types_tool = api.get_tool("portal_types")
    if types_tool is None:
        raise RuntimeError("portal_types tool not found")
    ensure_allowed_content_type(types_tool, "Plone Site", ROOT_TYPE)


def ensure_allowed_content_type(types_tool, type_name, allowed_type):
    """将指定内容类型加入允许列表。"""
    fti = types_tool.getTypeInfo(type_name)
    if fti is None:
        raise RuntimeError("FTI '%s' not found" % type_name)

    allowed = list(getattr(fti, "allowed_content_types", ()) or ())
    if allowed_type in allowed:
        logger.info("Skip allowed_content_types update for '%s' -> '%s'", type_name, allowed_type)
        return

    allowed.append(allowed_type)
    fti.manage_changeProperties(allowed_content_types=tuple(allowed))
    logger.info("Added '%s' to allowed_content_types of '%s'", allowed_type, type_name)


def setup_site_structure(portal):
    """创建根容器。"""
    logger.info("*** Setup Testmodel Site Structure ***")
    with ploneapi.env.adopt_roles(["Manager"]):
        if ROOT_ID not in portal:
            ploneapi.content.create(
                container=portal,
                type=ROOT_TYPE,
                id=ROOT_ID,
                title=ROOT_TITLE,
            )
            logger.info("Created root container '%s'", ROOT_ID)
        else:
            logger.info("Skip existing root container '%s'", ROOT_ID)

    root_container = portal.get(ROOT_ID)
    if root_container is None:
        raise RuntimeError("Failed to create root container '%s'" % ROOT_ID)
    return root_container


def setup_permissions(root_container):
    """设置根容器权限。"""
    logger.info("*** Setup Testmodel Permissions ***")
    roles = ["LabClerk", "LabManager", "Manager", "Owner"]
    root_container.manage_permission("View", roles=roles, acquire=0)
    root_container.manage_permission("Access contents information", roles=roles, acquire=0)
    root_container.reindexObjectSecurity()
    logger.info("Updated permissions for '%s'", api.get_path(root_container))


def setup_sidebar():
    """注册到 SENAITE 侧边栏。"""
    logger.info("*** Setup Testmodel Sidebar ***")
    setup_tool = api.get_senaite_setup()
    if setup_tool is None:
        raise RuntimeError("SENAITE setup tool not found")

    folders = list(setup_tool.getSidebarFolders())
    if ROOT_ID not in folders:
        folders.append(ROOT_ID)
        setup_tool.setSidebarFolders(tuple(folders))
        logger.info("Added '%s' to SENAITE sidebar", ROOT_ID)
    else:
        logger.info("Skip existing sidebar folder '%s'", ROOT_ID)


def uninstall_handler(context):
    """标准插件卸载入口。"""
    uninstall_file = "%s-uninstall.txt" % PROJECTNAME
    if context.readDataFile(uninstall_file) is None:
        return

    logger.info("Maitux.Testmodel uninstall handler [BEGIN]")
    setup_tool = api.get_senaite_setup()
    if setup_tool is None:
        raise RuntimeError("SENAITE setup tool not found")

    folders = list(setup_tool.getSidebarFolders())
    if ROOT_ID in folders:
        folders.remove(ROOT_ID)
        setup_tool.setSidebarFolders(tuple(folders))
        logger.info("Removed '%s' from SENAITE sidebar", ROOT_ID)
    else:
        logger.info("Skip missing sidebar folder '%s'", ROOT_ID)
    logger.info("Maitux.Testmodel uninstall handler [DONE]")


def post_install(context):
    """兼容旧入口。"""
    logger.info("Maitux.Testmodel post install handler [BEGIN]")
    portal = api.get_portal()
    run_install_steps(portal)
    logger.info("Maitux.Testmodel post install handler [DONE]")


def setup_testmodel_content(context):
    """兼容旧入口，统一委托到标准安装入口。"""
    setup_handler(context)


def uninstall(context):
    """兼容旧入口，统一委托到标准卸载入口。"""
    uninstall_handler(context)
