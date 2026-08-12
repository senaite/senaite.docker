# -*- coding: utf-8 -*-
"""安装/卸载处理器

标准插件模式：
  1. default profile 安装 XML 配置
  2. GenericSetup importStep 调用 setup_handler()
  3. setup_handler() 编排 Python 安装逻辑
  4. uninstall profile 调用 uninstall_handler()
"""

from bika.lims import api
from plone import api as ploneapi
from Products.CMFPlone.interfaces import INonInstallable
from senaite.core import logger
from senaite.core.api.workflow import update_workflow
from zope.interface import implementer

from maitux.workflow.config import PROJECTNAME

REACTIVATE_PERMISSION = "maitux.workflow: Transition: Reactivate"
SAMPLE_WORKFLOW_ID = "senaite_sample_workflow"
ANALYSIS_WORKFLOW_ID = "senaite_analysis_workflow"
REACTIVATE_ROLES = ("LabManager", "Manager")
WORKFLOW_ROOT_ID = "workflowroot"

SAMPLE_STATE_TRANSITIONS = {
    "verified": [
        "publish", "invalidate", "rollback_to_receive", "detach",
        "reattach", "create_partitions", "dispatch", "multi_results",
        "duplicate_sample", "reactivate",
    ],
    "published": [
        "republish", "invalidate", "create_partitions", "dispatch",
        "multi_results", "duplicate_sample", "reactivate",
    ],
}

ANALYSIS_STATE_TRANSITIONS = {
    "to_be_verified": [
        "multi_verify", "verify", "retest", "retract", "reject", "reactivate",
    ],
    "verified": [
        "publish", "reactivate",
    ],
    "published": [
        "reactivate",
    ],
}

SAMPLE_STATE_PERMISSIONS = {
    "verified": {
        "senaite.core: Transition: Publish Results": (1, ()),
        "senaite.core: Transition: Invalidate": (1, ()),
        "senaite.core: Transition: Create Partitions": (1, ()),
    },
}

ANALYSIS_STATE_PERMISSIONS = {
    "to_be_verified": {
        "senaite.core: Transition: Retest": (1, ()),
        "senaite.core: Transition: Verify": (0, ("LabManager", "Manager", "Verifier")),
        "senaite.core: Transition: Retract": (
            0, ("Analyst", "LabManager", "Manager", "Sampler")),
        "senaite.core: Transition: Reject Analysis": (1, ()),
    },
    "verified": {
        "senaite.core: Transition: Publish Results": (1, ()),
    },
}


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

    logger.info("Maitux.Workflow setup handler [BEGIN]")
    portal = context.getSite()
    run_install_steps(portal)
    logger.info("Maitux.Workflow setup handler [DONE]")


def run_install_steps(portal):
    """按精简方式编排安装步骤，仅保留 workflow patch 并清理旧导航入口。"""
    cleanup_sidebar()
    setup_workflows()


def setup_type_constraints():
    """先检查再修改类型约束，不依赖 try/except 做幂等。"""
    logger.info("*** Setup Workflow Type Constraints ***")
    types_tool = api.get_tool("portal_types")
    if types_tool is None:
        raise RuntimeError("portal_types tool not found")
    ensure_allowed_content_type(types_tool, "Plone Site", "WorkflowContainer")


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
    logger.info("*** Setup Workflow Site Structure ***")
    root_id = "workflowroot"

    with ploneapi.env.adopt_roles(['Manager']):
        if root_id not in portal:
            ploneapi.content.create(
                container=portal,
                type='WorkflowContainer',
                id=root_id,
                title='Workflow Management'
            )
            logger.info("Created root container '%s'", root_id)
        else:
            logger.info("Skip existing root container '%s'", root_id)

    root_container = portal.get(root_id)
    if root_container is None:
        raise RuntimeError("Failed to create root container '%s'" % root_id)
    return root_container


def setup_permissions(root_container):
    """设置根容器权限。"""
    logger.info("*** Setup Workflow Permissions ***")
    roles = ["LabClerk", "LabManager", "Manager", "Owner"]
    root_container.manage_permission("View", roles=roles, acquire=0)
    root_container.manage_permission("Access contents information", roles=roles, acquire=0)
    root_container.reindexObjectSecurity()
    logger.info("Updated permissions for '%s'", api.get_path(root_container))


def setup_sidebar():
    """注册到 SENAITE 侧边栏。"""
    logger.info("*** Setup Workflow Sidebar ***")
    setup_tool = api.get_senaite_setup()
    if setup_tool is None:
        raise RuntimeError("SENAITE setup tool not found")

    folders = list(setup_tool.getSidebarFolders())
    if WORKFLOW_ROOT_ID not in folders:
        folders.append(WORKFLOW_ROOT_ID)
        setup_tool.setSidebarFolders(tuple(folders))
        logger.info("Added '%s' to SENAITE sidebar", WORKFLOW_ROOT_ID)
    else:
        logger.info("Skip existing sidebar folder '%s'", WORKFLOW_ROOT_ID)


def cleanup_sidebar():
    """移除历史遗留的 workflowroot 侧栏入口，避免继续显示左侧导航。"""
    logger.info("*** Cleanup Workflow Sidebar ***")
    setup_tool = api.get_senaite_setup()
    if setup_tool is None:
        raise RuntimeError("SENAITE setup tool not found")

    folders = list(setup_tool.getSidebarFolders())
    if WORKFLOW_ROOT_ID not in folders:
        logger.info("Skip missing sidebar folder '%s'", WORKFLOW_ROOT_ID)
        return

    folders.remove(WORKFLOW_ROOT_ID)
    setup_tool.setSidebarFolders(tuple(folders))
    logger.info("Removed '%s' from SENAITE sidebar", WORKFLOW_ROOT_ID)


def setup_workflows():
    """以 Python patch 方式补充 reactivate 转换，避免覆盖整份官方 workflow。"""
    logger.info("*** Setup Reactivate Workflows ***")
    workflow_tool = api.get_tool("portal_workflow")
    if workflow_tool is None:
        raise RuntimeError("portal_workflow tool not found")

    sample_workflow = workflow_tool.getWorkflowById(SAMPLE_WORKFLOW_ID)
    if sample_workflow is None:
        raise RuntimeError("Workflow '%s' not found" % SAMPLE_WORKFLOW_ID)

    analysis_workflow = workflow_tool.getWorkflowById(ANALYSIS_WORKFLOW_ID)
    if analysis_workflow is None:
        raise RuntimeError("Workflow '%s' not found" % ANALYSIS_WORKFLOW_ID)

    # 样品发布态补充 reactivate 按钮及对应权限映射。
    update_workflow(
        sample_workflow,
        states={
            "verified": {
                "transitions": ["reactivate"],
                "permissions": {
                    REACTIVATE_PERMISSION: REACTIVATE_ROLES,
                },
            },
            "published": {
                "transitions": ["reactivate"],
                "permissions": {
                    REACTIVATE_PERMISSION: REACTIVATE_ROLES,
                },
            },
        },
        transitions={
            "reactivate": {
                "title": "Reactivate",
                "new_state": "sample_received",
                "action": "Reactivate",
                "action_url": "",
                "after_script": "",
                "guard": {
                    "guard_permissions": REACTIVATE_PERMISSION,
                },
            },
        },
    )
    # 某些 live 站点上 update_workflow 不会稳定刷新 state.transitions，这里强制校正。
    ensure_state_reactivate_setup(
        sample_workflow, "verified", SAMPLE_STATE_TRANSITIONS["verified"])
    ensure_state_reactivate_setup(
        sample_workflow, "published", SAMPLE_STATE_TRANSITIONS["published"])
    ensure_state_permission_setup(
        sample_workflow, "verified", SAMPLE_STATE_PERMISSIONS["verified"])

    # 分析项统一只保留一个 Reactivate，回退到 assigned。
    update_workflow(
        analysis_workflow,
        states={
            "to_be_verified": {
                "transitions": ["reactivate"],
                "permissions": {
                    REACTIVATE_PERMISSION: REACTIVATE_ROLES,
                },
            },
            "verified": {
                "transitions": ["reactivate"],
                "permissions": {
                    REACTIVATE_PERMISSION: REACTIVATE_ROLES,
                },
            },
            "published": {
                "transitions": ["reactivate"],
                "permissions": {
                    REACTIVATE_PERMISSION: REACTIVATE_ROLES,
                },
            },
        },
        transitions={
            "reactivate": {
                "title": "Reactivate",
                "new_state": "assigned",
                "action": "Reactivate",
                "action_url": "",
                "after_script": "",
                "guard": {
                    "guard_permissions": REACTIVATE_PERMISSION,
                },
            },
        },
    )
    # 显式修正 Analysis workflow 的状态出口，并清理历史残留的 reactivate_assigned。
    ensure_state_reactivate_setup(
        analysis_workflow, "to_be_verified", ANALYSIS_STATE_TRANSITIONS["to_be_verified"])
    ensure_state_reactivate_setup(
        analysis_workflow, "verified", ANALYSIS_STATE_TRANSITIONS["verified"])
    ensure_state_reactivate_setup(
        analysis_workflow, "published", ANALYSIS_STATE_TRANSITIONS["published"])
    ensure_state_permission_setup(
        analysis_workflow, "to_be_verified", ANALYSIS_STATE_PERMISSIONS["to_be_verified"])
    ensure_state_permission_setup(
        analysis_workflow, "verified", ANALYSIS_STATE_PERMISSIONS["verified"])
    logger.info("Reactivate workflow patches applied")


def ensure_state_reactivate_setup(workflow, state_id, transition_ids):
    """强制修正指定状态的 transition 列表与权限映射。"""
    state = workflow.states.get(state_id)
    if state is None:
        raise RuntimeError("Workflow state '%s' not found in '%s'" % (state_id, workflow.id))

    # 直接恢复为最终允许的完整出口清单，确保已被错误覆盖的 live workflow 也能修复回来。
    state.transitions = tuple(transition_ids)

    workflow.permissions = tuple(sorted(set(workflow.permissions + (REACTIVATE_PERMISSION,))))
    state.setPermission(REACTIVATE_PERMISSION, 0, REACTIVATE_ROLES)
    logger.info("Ensured workflow state '%s.%s' transitions=%s",
                workflow.id, state_id, state.transitions)


def ensure_state_permission_setup(workflow, state_id, permission_map):
    """恢复指定状态下关键原生 transition 的权限映射。"""
    state = workflow.states.get(state_id)
    if state is None:
        raise RuntimeError("Workflow state '%s' not found in '%s'" % (state_id, workflow.id))

    for permission_id, value in permission_map.items():
        acquired, roles = value
        if permission_id not in workflow.permissions:
            workflow.permissions = workflow.permissions + (permission_id,)
        state.setPermission(permission_id, acquired, roles)


def uninstall_handler(context):
    """标准插件卸载入口。"""
    uninstall_file = "%s-uninstall.txt" % PROJECTNAME
    if context.readDataFile(uninstall_file) is None:
        return

    logger.info("Maitux.Workflow uninstall handler [BEGIN]")
    cleanup_sidebar()

    logger.info("Maitux.Workflow uninstall handler [DONE]")


def setup_workflow_content(context):
    """兼容旧入口，统一委托到标准安装入口。"""
    setup_handler(context)


def uninstall(context):
    """兼容旧入口，统一委托到标准卸载入口。"""
    uninstall_handler(context)
