# -*- coding: utf-8 -*-
"""审核分配安装/卸载处理器"""

from bika.lims import api
from plone import api as ploneapi
from Products.CMFPlone.interfaces import INonInstallable
from senaite.core import logger
from senaite.core.api import catalog as catalogapi
from senaite.core.catalog import WORKSHEET_CATALOG
from zope.interface import implementer

from maitux.reviewerassignment.config import PROJECTNAME
from maitux.reviewerassignment.config import REVIEWER_FIELD
from maitux.reviewerassignment.config import REVIEWER_INDEX
from maitux.reviewerassignment.config import ROOT_ID
from maitux.reviewerassignment.config import ROOT_TITLE
from maitux.reviewerassignment.config import VERIFIER_ROLE
from maitux.reviewerassignment.config import WORKSHEET_REVIEWER_BEHAVIOR


# 本 addon 不再改动 workflow。
#
# 曾经这里有一个 setup_workflows()，用 state.setPermission() / state.transitions
# 直接写 live workflow。逐项比对 SENAITE 原生 definition.xml 后确认：7 项里 6 项
# 是原生值照抄（analysis 与 worksheet 的状态出口、Retract / Retest / Reject 权限），
# 唯一的真改动是把 analysis "to_be_verified" 的 Verify 权限从原生的
# [LabManager, Manager, Verifier] 收窄成 [Verifier]。
#
# 那是越界：该权限归 maitux.workflow 管（它设的正是原生值）。两个 addon 同写一个
# 权限，谁的 profile 后跑谁赢，导致同一套代码在不同站点表现不一致。
#
# 详见 Docs/maitux.reviewerassignment-遗留问题分阶段整改方案.md 阶段 A。


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

    logger.info("Maitux.Reviewerassignment setup handler [BEGIN]")
    portal = context.getSite()
    run_install_steps(portal)
    logger.info("Maitux.Reviewerassignment setup handler [DONE]")


def run_install_steps(portal):
    """按标准插件方式编排安装步骤"""
    setup_type_constraints()
    setup_behaviors()
    setup_catalog()
    root_container = setup_site_structure(portal)
    setup_permissions(root_container)
    setup_sidebar()
    check_site_prerequisites()


def check_site_prerequisites():
    """检查站点设置是否会让本 addon 的审核人机制失效，只告警不阻断。

    审核人机制只覆盖「工作表内」的分析项 —— guard 在拿不到工作表时一律放行。
    真正把普通分析员挡在工作表之外的，是 SENAITE 自己的
    `AllowToSubmitNotAssigned=False`（提交前必须有分析员，而分析员只能由工作表带来）。

    该设置一旦被打开，不建工作表也能提交，本 addon 的约束就整体形同虚设。
    这里不去覆盖 SENAITE 的设置，只在安装时把风险显式说出来。
    """
    logger.info("*** Check Reviewerassignment Site Prerequisites ***")
    setup_tool = api.get_bika_setup()
    if setup_tool is None:
        logger.warn("Maitux.Reviewerassignment: bika_setup not found, "
                    "skip prerequisite check")
        return

    try:
        allow_not_assigned = setup_tool.getAllowToSubmitNotAssigned()
    except Exception:
        logger.warn("Maitux.Reviewerassignment: cannot read "
                    "AllowToSubmitNotAssigned, skip prerequisite check")
        return

    if allow_not_assigned:
        logger.warn(
            "Maitux.Reviewerassignment: site setting "
            "'AllowToSubmitNotAssigned' is enabled. Analyses can be submitted "
            "without a worksheet, and this add-on's reviewer rules only cover "
            "analyses inside a worksheet -- the reviewer requirement can be "
            "bypassed entirely. Disable it in Setup > Analyses to keep the "
            "reviewer assignment effective.")
    else:
        logger.info("Maitux.Reviewerassignment: 'AllowToSubmitNotAssigned' is "
                    "disabled, reviewer rules cover the submit path")


def setup_type_constraints():
    """先检查再修改类型约束，不依赖 try/except 做幂等"""
    logger.info("*** Setup Reviewerassignment Type Constraints ***")
    types_tool = api.get_tool("portal_types")
    if types_tool is None:
        raise RuntimeError("portal_types tool not found")
    ensure_allowed_content_type(types_tool, "Plone Site", "ReviewerassignmentContainer")


def setup_behaviors():
    """启用 Worksheet 审核人行为"""
    logger.info("*** Setup Reviewerassignment Behaviors ***")
    api.enable_behavior("Worksheet", WORKSHEET_REVIEWER_BEHAVIOR)


def setup_catalog():
    """为工作表 catalog 增加审核人索引和 metadata"""
    logger.info("*** Setup Reviewerassignment Catalog ***")
    catalog = api.get_tool(WORKSHEET_CATALOG)
    if catalog is None:
        raise RuntimeError("Worksheet catalog not found")

    catalogapi.add_index(catalog, REVIEWER_INDEX, "FieldIndex")
    catalogapi.add_column(catalog, REVIEWER_INDEX)
    catalogapi.reindex_index(catalog, REVIEWER_INDEX)


def ensure_allowed_content_type(types_tool, type_name, allowed_type):
    """将指定内容类型加入允许列表"""
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
    """创建根容器"""
    logger.info("*** Setup Reviewerassignment Site Structure ***")
    with ploneapi.env.adopt_roles(['Manager']):
        if ROOT_ID not in portal:
            root_container = ploneapi.content.create(
                container=portal,
                type='ReviewerassignmentContainer',
                id=ROOT_ID,
                title=ROOT_TITLE
            )
            logger.info("Created root container '%s'", ROOT_ID)
        else:
            root_container = portal.get(ROOT_ID)
            root_container.setTitle(ROOT_TITLE)
            root_container.reindexObject()
            logger.info("Updated root container '%s'", ROOT_ID)

    root_container = portal.get(ROOT_ID)
    if root_container is None:
        raise RuntimeError("Failed to create root container '%s'" % ROOT_ID)
    return root_container


def setup_permissions(root_container):
    """设置根容器权限"""
    logger.info("*** Setup Reviewerassignment Permissions ***")
    roles = [VERIFIER_ROLE, "LabManager", "Manager", "Owner"]
    root_container.manage_permission("View", roles=roles, acquire=0)
    root_container.manage_permission("Access contents information", roles=roles, acquire=0)
    root_container.reindexObjectSecurity()
    logger.info("Updated permissions for '%s'", api.get_path(root_container))


def setup_sidebar():
    """注册到 SENAITE 侧边栏"""
    logger.info("*** Setup Reviewerassignment Sidebar ***")
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
    """标准插件卸载入口"""
    uninstall_file = "%s-uninstall.txt" % PROJECTNAME
    if context.readDataFile(uninstall_file) is None:
        return

    logger.info("Maitux.Reviewerassignment uninstall handler [BEGIN]")
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

    logger.info("Maitux.Reviewerassignment uninstall handler [DONE]")


def setup_reviewerassignment_content(context):
    """兼容旧入口，统一委托到标准安装入口。"""
    setup_handler(context)


def uninstall(context):
    """兼容旧入口，统一委托到标准卸载入口。"""
    uninstall_handler(context)
