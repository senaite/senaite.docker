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


ANALYSIS_WORKFLOW_ID = "senaite_analysis_workflow"
WORKSHEET_WORKFLOW_ID = "senaite_worksheet_workflow"

ANALYSIS_TO_BE_VERIFIED_TRANSITIONS = (
    "multi_verify",
    "verify",
    "retest",
    "retract",
    "reject",
)
WORKSHEET_OPEN_TRANSITIONS = ("submit", "remove")
WORKSHEET_TO_BE_VERIFIED_TRANSITIONS = ("verify", "retract", "rollback_to_open")

ANALYSIS_PERMISSION_VERIFY = "senaite.core: Transition: Verify"
ANALYSIS_PERMISSION_RETEST = "senaite.core: Transition: Retest"
ANALYSIS_PERMISSION_RETRACT = "senaite.core: Transition: Retract"
ANALYSIS_PERMISSION_REJECT = "senaite.core: Transition: Reject Analysis"


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
    setup_workflows()


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


def setup_workflows():
    """安全修补 live workflow，避免覆盖官方 workflow XML"""
    logger.info("*** Setup Reviewerassignment Workflows ***")
    workflow_tool = api.get_tool("portal_workflow")
    if workflow_tool is None:
        raise RuntimeError("portal_workflow tool not found")

    analysis_workflow = workflow_tool.getWorkflowById(ANALYSIS_WORKFLOW_ID)
    worksheet_workflow = workflow_tool.getWorkflowById(WORKSHEET_WORKFLOW_ID)
    if analysis_workflow is None:
        raise RuntimeError("Workflow '%s' not found" % ANALYSIS_WORKFLOW_ID)
    if worksheet_workflow is None:
        raise RuntimeError("Workflow '%s' not found" % WORKSHEET_WORKFLOW_ID)

    ensure_state_transitions(
        analysis_workflow,
        "to_be_verified",
        ANALYSIS_TO_BE_VERIFIED_TRANSITIONS)
    ensure_state_transitions(
        worksheet_workflow,
        "open",
        WORKSHEET_OPEN_TRANSITIONS)
    ensure_state_transitions(
        worksheet_workflow,
        "to_be_verified",
        WORKSHEET_TO_BE_VERIFIED_TRANSITIONS)

    ensure_state_permission_setup(
        analysis_workflow,
        "to_be_verified",
        {
            ANALYSIS_PERMISSION_VERIFY: (0, (VERIFIER_ROLE, )),
            ANALYSIS_PERMISSION_RETEST: (1, ()),
            ANALYSIS_PERMISSION_RETRACT: (0, ("Analyst", "LabManager", "Manager", "Sampler")),
            ANALYSIS_PERMISSION_REJECT: (1, ()),
        })


def ensure_state_transitions(workflow, state_id, transition_ids):
    """恢复指定状态的完整出口列表"""
    state = workflow.states.get(state_id)
    if state is None:
        raise RuntimeError("Workflow state '%s' not found in '%s'" % (state_id, workflow.id))
    state.transitions = tuple(transition_ids)
    logger.info("Ensured workflow state '%s.%s' transitions=%s",
                workflow.id, state_id, state.transitions)


def ensure_state_permission_setup(workflow, state_id, permission_map):
    """恢复指定状态的关键权限映射"""
    state = workflow.states.get(state_id)
    if state is None:
        raise RuntimeError("Workflow state '%s' not found in '%s'" % (state_id, workflow.id))

    for permission_id, value in permission_map.items():
        acquired, roles = value
        if permission_id not in workflow.permissions:
            workflow.permissions = workflow.permissions + (permission_id,)
        state.setPermission(permission_id, acquired, roles)


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
