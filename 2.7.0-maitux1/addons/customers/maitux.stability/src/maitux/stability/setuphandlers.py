# -*- coding: utf-8 -*-
from bika.lims import api
from plone import api as ploneapi
from datetime import timedelta
from DateTime import DateTime
from Products.CMFPlone.interfaces import INonInstallable
try:
    from Products.CMFPlone.utils import safe_unicode
except Exception:
    safe_unicode = None
from senaite.core import logger
from senaite.core.upgrade.utils import temporary_allow_type
from zope.interface import implementer

from maitux.stability import _
from maitux.stability.permissions import AddStabilityPlanTemplate


MODULE_ID = "stability_studies"
MODULE_TITLE = _(u"Stability Studies", default=u"Stability Studies")
MODULE_TYPE = "StabilityStudies"
DEFAULT_STUDY_ID = "default_stability_study"
DEFAULT_STUDY_TITLE = _(u"Default Stability Study", default=u"Default Stability Study")
DEFAULT_STUDY_TYPE = "StabilityStudy"
# sidebar 当前对子级使用 path 倒序查询，这里通过数字前缀稳定控制显示顺序。
# 同时保留旧 ID 别名，方便历史数据在升级/卸载时统一清理。
TABLE_DEFINITIONS = (
    ("storage_conditions", "500_storage_conditions", "Storage Conditions", "StorageConditions", ("storage_conditions", "z_storage_conditions")),
    ("packaging_specifications", "400_packaging_specifications", "Packaging Specifications", "PackagingSpecifications", ("packaging_specifications", "y_packaging_specifications")),
    ("stability_plan_templates", "300_stability_plan_templates", "Stability Plan Templates", "StabilityPlanTemplates", ("stability_plan_templates", "x_stability_plan_templates")),
    ("stability_plans", "200_stability_plans", "Stability Plans", "StabilityPlans", ("stability_plans", "w_stability_plans")),
    ("task_board", "100_task_board", "Task Board", "StabilityPlans", ("task_board", "v_task_board")),
)
TABLE_ID_BY_LOGICAL = dict([(item[0], item[1]) for item in TABLE_DEFINITIONS])
TABLE_ID_ALIASES = dict([(item[1], item[4]) for item in TABLE_DEFINITIONS])
STATIC_TABLES = tuple([(item[1], item[2], item[3]) for item in TABLE_DEFINITIONS])
SIDEBAR_DEPTH = 2
PROJECTNAME = "maitux.stability"


def _table_title(title):
    """把静态表标题转为 maitux.stability 域的 Message，供侧边栏等运行时翻译。"""
    return _(title, default=title)


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

    logger.info("MAITUX Stability Studies setup handler [BEGIN]")
    portal = context.getSite()
    _setup_stability_content(portal)
    logger.info("MAITUX Stability Studies setup handler [DONE]")


def post_install(context):
    logger.info("MAITUX Stability Studies post install handler [BEGIN]")
    portal = api.get_portal()
    _setup_stability_content(portal)
    logger.info("MAITUX Stability Studies post install handler [DONE]")


def setup_stability_content(context):
    """兼容旧入口，统一委托到标准安装入口。"""
    setup_handler(context)


def _candidate_ids(value):
    canonical = TABLE_ID_BY_LOGICAL.get(value, value)
    related = [canonical]
    aliases = TABLE_ID_ALIASES.get(canonical, ())
    related.extend(aliases)
    candidates = []
    for related_value in related:
        for v in (
            related_value,
            related_value.replace("_", "-"),
            related_value.replace("-", "_"),
        ):
            if v and v not in candidates:
                candidates.append(v)
    return candidates


def _setup_stability_content(portal):
    def object_label(obj):
        """返回对象标识，便于安装日志定位问题对象。"""
        if obj is None:
            return "<missing>"
        try:
            return api.get_path(obj)
        except Exception:
            return repr(obj)

    def prune_container_refs(container, obj_id):
        if container is None or not obj_id:
            return
        for attr in ("_ordering", "_order"):
            order = getattr(container, attr, None)
            if not order:
                continue
            try:
                while obj_id in order:
                    order.remove(obj_id)
            except Exception:
                pass
        try:
            mt_index = getattr(container, "_mt_index", None)
            if mt_index:
                for mt, ids in mt_index.items():
                    try:
                        while obj_id in ids:
                            ids.remove(obj_id)
                    except Exception:
                        pass
        except Exception:
            pass

    def scrub_missing_children(container):
        if container is None:
            return
        try:
            child_ids = list(getattr(container, "objectIds", lambda: [])())
        except Exception:
            child_ids = []
        for child_id in child_ids:
            try:
                obj = container.get(child_id)
            except Exception:
                obj = None
            if obj is not None:
                continue
            prune_container_refs(container, child_id)
            try:
                tree = getattr(container, "_tree", None)
                if tree is not None and child_id in tree:
                    del tree[child_id]
            except Exception:
                pass
            logger.info("Pruned missing child reference '%s' from %s", child_id, api.get_path(container))

    def ensure_fti_permissions():
        types_tool = api.get_tool("portal_types")
        if not types_tool:
            return
        fti = types_tool.getTypeInfo("StabilityPlanTemplate")
        if fti is None:
            return
        try:
            value = getattr(fti, "add_permission", None)
            if value != "maitux.stability.permissions.AddStabilityPlanTemplate":
                setter = getattr(fti, "_setPropValue", None)
                if callable(setter):
                    setter("add_permission", "maitux.stability.permissions.AddStabilityPlanTemplate")
                else:
                    fti.manage_changeProperties(add_permission="maitux.stability.permissions.AddStabilityPlanTemplate")
        except Exception:
            logger.exception(
                "Failed to configure add_permission for StabilityPlanTemplate FTI"
            )
            raise

    def force_setup_like_permissions(obj):
        if obj is None:
            return
        # 这些权限属于核心安装配置，失败后必须中断安装，避免站点处于半配置状态。
        permission_rules = (
            ("View", ["Authenticated"]),
            ("Access contents information", ["Authenticated"]),
            ("List folder contents", ["Authenticated"]),
            ("Modify portal content", ["LabClerk", "LabManager", "Manager"]),
            ("Add portal content", ["LabClerk", "LabManager", "Manager"]),
            (
                AddStabilityPlanTemplate,
                ["LabClerk", "LabManager", "Manager", "Owner"],
            ),
        )
        for permission, roles in permission_rules:
            try:
                obj.manage_permission(permission, roles=roles, acquire=False)
            except Exception:
                logger.exception(
                    "Failed to set permission '%s' on %s",
                    permission,
                    object_label(obj),
                )
                raise

    def ensure_permissions():
        roles = ["LabClerk", "LabManager", "Manager", "Owner"]
        try:
            portal.manage_permission(AddStabilityPlanTemplate, roles=roles, acquire=False)
        except Exception:
            logger.exception(
                "Failed to register portal permission '%s'",
                AddStabilityPlanTemplate,
            )
            raise

    def bind_workflows():
        wf_tool = api.get_tool("portal_workflow")
        if wf_tool is None:
            raise RuntimeError("portal_workflow tool not found")

        bindings = (
            (
                (
                    "StabilityPlanTemplate",
                    "StorageCondition",
                    "PackagingSpecification",
                ),
                ("senaite_deactivable_type_workflow",),
            ),
            (
                (
                    "StabilityStudies",
                    "StorageConditions",
                    "PackagingSpecifications",
                    "StabilityPlanTemplates",
                    "StabilityPlans",
                ),
                ("senaite_setup_workflow",),
            ),
            (
                ("StabilityStudy",),
                ("senaite_one_state_workflow",),
            ),
            (
                (
                    "StabilityPlan",
                    "StabilityTimepointTask",
                ),
                ("senaite_one_state_workflow",),
            ),
        )
        for portal_types, workflows in bindings:
            try:
                wf_tool.setChainForPortalTypes(portal_types, workflows)
            except Exception:
                logger.exception(
                    "Failed to bind workflows %s to portal types %s",
                    ", ".join(workflows),
                    ", ".join(portal_types),
                )
                raise

    def update_security(obj):
        try:
            wf_tool = api.get_tool("portal_workflow")
        except Exception:
            wf_tool = None

        if wf_tool is not None:
            try:
                # Ensure object is in 'active' state if it has no state
                if not api.get_review_status(obj):
                    wf_tool.setStatusOf("senaite_setup_workflow", obj, {
                        "review_state": "active",
                        "action": None,
                        "actor": "admin",
                        "time": DateTime(),
                        "comments": "Initial state",
                    })
                wf_tool.updateRoleMappingsFor(obj)
            except Exception:
                pass

        try:
            obj.reindexObject(idxs=["allowedRolesAndUsers"])
        except Exception:
            pass

    def apply_constraints(obj, allowed_types):
        try:
            types_tool = api.get_tool("portal_types")
            if types_tool:
                fti = types_tool.getTypeInfo(api.get_portal_type(obj))
            else:
                fti = None
        except Exception:
            fti = None

        behavior_id = "plone.constraintypes"

        if fti is not None and behavior_id:
            try:
                behaviors = list(getattr(fti, "behaviors", ()) or ())
                if behavior_id not in behaviors:
                    behaviors.append(behavior_id)
                    fti.behaviors = tuple(behaviors)
            except Exception:
                pass

        candidates = []
        try:
            from Products.CMFPlone.interfaces.constrains import ISelectableConstrainTypes
            candidates.append(ISelectableConstrainTypes)
        except Exception:
            pass
        try:
            from plone.app.dexterity.behaviors.constrains import ISelectableConstrainTypes
            candidates.append(ISelectableConstrainTypes)
        except Exception:
            pass
        try:
            from plone.app.content.interfaces import ISelectableConstrainTypes
            candidates.append(ISelectableConstrainTypes)
        except Exception:
            pass

        for iface in candidates:
            adapter = None
            try:
                adapter = iface(obj, None)
            except Exception:
                adapter = None

            if adapter is None:
                continue

            set_mode = getattr(adapter, "setConstrainTypesMode", None)
            set_local = getattr(adapter, "setLocallyAllowedTypes", None)
            set_addable = getattr(adapter, "setImmediatelyAddableTypes", None)
            if not callable(set_mode) or not callable(set_local) or not callable(set_addable):
                continue

            try:
                types = list(allowed_types)
                if safe_unicode is not None:
                    try:
                        types = map(safe_unicode, types)
                    except Exception:
                        pass

                adapter.setConstrainTypesMode(1)
                adapter.setLocallyAllowedTypes(types)
                adapter.setImmediatelyAddableTypes(types)

                try:
                    if not adapter.getLocallyAllowedTypes():
                        adapter.setLocallyAllowedTypes(tuple(types))
                        adapter.setImmediatelyAddableTypes(tuple(types))
                except Exception:
                    pass

                try:
                    if not adapter.getLocallyAllowedTypes():
                        adapter.setConstrainTypesMode(2)
                except Exception:
                    pass
                return True
            except Exception:
                pass
        return False

    types_tool = api.get_tool("portal_types")
    if not types_tool:
        return

    ensure_permissions()
    ensure_fti_permissions()
    bind_workflows()

    required_types = [MODULE_TYPE, DEFAULT_STUDY_TYPE]
    required_types.extend([t[2] for t in STATIC_TABLES])
    for portal_type in required_types:
        if types_tool.getTypeInfo(portal_type) is None:
            logger.warning(
                "Type '%s' not found in portal_types. Skipping stability setup.",
                portal_type,
            )
            return

    def cleanup_stale_entries(obj):
        obj_uid = api.get_uid(obj)
        obj_path = api.get_path(obj)
        portal_path = api.get_path(portal)
        for tool_name in ("portal_catalog", "uid_catalog"):
            try:
                tool = api.get_tool(tool_name)
                if tool is None:
                    continue
                brains = tool(
                    UID=obj_uid,
                    sort_on="path",
                )
                for brain in brains:
                    brain_path = brain.getPath()
                    if brain_path != obj_path:
                        try:
                            tool.uncatalog_object(brain_path)
                            logger.info(
                                "Removed stale %s entry for %s: %s",
                                tool_name, obj_uid, brain_path,
                            )
                        except Exception:
                            pass
                if tool_name == "uid_catalog":
                    stale = tool(
                        portal_type=api.get_portal_type(obj),
                        path={"query": portal_path, "depth": 3},
                    )
                    for brain in stale:
                        if api.get_uid(brain) == obj_uid:
                            continue
                        if api.get_title(brain) != api.get_title(obj):
                            continue
                        try:
                            brain.getObject()
                        except Exception:
                            try:
                                tool.uncatalog_object(brain.getPath())
                            except Exception:
                                pass
            except Exception:
                pass

    def recatalog(obj):
        try:
            obj.reindexObject()
        except Exception:
            pass
        for tool_name in ("portal_catalog", "uid_catalog"):
            try:
                tool = api.get_tool(tool_name)
                if tool:
                    tool.catalog_object(obj, api.get_path(obj))
            except Exception:
                pass
        cleanup_stale_entries(obj)

    def migrate_alias_children(source, target):
        if source is None or target is None or source == target:
            return
        try:
            source_ids = list(getattr(source, "objectIds", lambda: [])())
        except Exception:
            source_ids = []
        try:
            target_ids = set(getattr(target, "objectIds", lambda: [])())
        except Exception:
            target_ids = set()

        # 升级过程中如果同时存在旧容器和新容器，先迁移子对象，
        # 避免业务数据残留在旧 ID 下。
        for child_id in source_ids:
            if child_id in target_ids:
                logger.warning(
                    "Skip moving duplicate child '%s' from %s to %s",
                    child_id,
                    api.get_path(source),
                    api.get_path(target),
                )
                continue
            try:
                clipboard = source.manage_cutObjects([child_id])
                target.manage_pasteObjects(clipboard)
                target_ids.add(child_id)
                logger.info(
                    "Moved stability child '%s' from %s to %s",
                    child_id,
                    api.get_path(source),
                    api.get_path(target),
                )
            except Exception as exc:
                logger.warning(
                    "Could not move stability child '%s' from %s to %s: %s",
                    child_id,
                    api.get_path(source),
                    api.get_path(target),
                    exc,
                )

    def merge_alias_objects(container, obj, obj_id):
        if container is None or obj is None:
            return obj

        canonical_id = api.get_id(obj) or obj_id
        is_task_board = canonical_id == TABLE_ID_BY_LOGICAL.get("task_board")

        for alias_id in _candidate_ids(obj_id):
            if alias_id == canonical_id:
                continue
            alias = container.get(alias_id)
            if alias is None:
                continue

            if is_task_board:
                try:
                    alias_children = list(getattr(alias, "objectIds", lambda: [])())
                except Exception:
                    alias_children = []
                # Task Board 鐞嗚涓婁笉鎵胯浇涓氬姟鏁版嵁锛涜嫢鍘嗗彶瀵硅薄涓嬩粛鏈夊唴瀹癸紝鍏堜繚鐣欏苟璁板綍鏃ュ織銆?                if alias_children:
                    logger.warning(
                        "Keeping old task board alias '%s' because it still contains children",
                        alias_id,
                    )
                    continue
            else:
                migrate_alias_children(alias, obj)

            try:
                container.manage_delObjects([alias_id])
                logger.info("Removed obsolete stability alias '%s'", alias_id)
            except Exception:
                prune_container_refs(container, alias_id)
        return obj

    def create_or_update(container, portal_type, obj_id, title):
        obj = None
        found_id = None
        for cid in _candidate_ids(obj_id):
            obj = container.get(cid)
            if obj is not None:
                found_id = cid
                break
        if obj is None:
            with temporary_allow_type(container, portal_type):
                obj = ploneapi.content.create(
                    container=container,
                    type=portal_type,
                    id=obj_id,
                    title=title,
                )
        elif found_id and found_id != obj_id and obj_id not in getattr(container, "objectIds", lambda: [])():
            try:
                old_id = found_id
                container.manage_renameObject(found_id, obj_id)
                obj = container.get(obj_id)
                found_id = obj_id
                logger.info("Renamed stability object '%s' -> '%s'", old_id, obj_id)
            except Exception:
                pass
        try:
            if getattr(obj, "Title", None) and obj.Title() != title:
                obj.setTitle(title)
        except Exception:
            pass
        obj = merge_alias_objects(container, obj, obj_id)
        recatalog(obj)
        force_setup_like_permissions(obj)
        update_security(obj)
        return obj

    def reorder_children(container, ordered_ids):
        if container is None or not hasattr(container, "moveObjectToPosition"):
            return
        position = 0
        for obj_id in ordered_ids:
            obj = None
            for cid in _candidate_ids(obj_id):
                obj = container.get(cid)
                if obj is not None:
                    obj_id = cid
                    break
            if obj is None:
                continue
            try:
                container.moveObjectToPosition(obj_id, position)
                position += 1
            except Exception as exc:
                logger.warning(
                    "Could not reorder stability child '%s' in %s: %s",
                    obj_id,
                    object_label(container),
                    exc,
                )

    def delete_if_exists(container, obj_id):
        if container is None:
            return
        for cid in _candidate_ids(obj_id):
            if cid in getattr(container, "objectIds", lambda: [])():
                try:
                    container.manage_delObjects([cid])
                    logger.info("Removed obsolete stability object '%s'", cid)
                except Exception:
                    prune_container_refs(container, cid)

    def delete_default_studies(container):
        def low_level_delete(obj_id):
            tree = getattr(container, "_tree", None)
            if tree is None:
                return False
            try:
                if obj_id not in tree:
                    prune_container_refs(container, obj_id)
                    return True
                del tree[obj_id]
            except Exception:
                prune_container_refs(container, obj_id)
                return False
            prune_container_refs(container, obj_id)
            return True

        if container is None:
            return
        try:
            child_ids = list(getattr(container, "objectIds", lambda: [])())
        except Exception:
            child_ids = []

        for child_id in child_ids:
            obj = container.get(child_id)
            if obj is None:
                if child_id in _candidate_ids(DEFAULT_STUDY_ID):
                    low_level_delete(child_id)
                continue
            if getattr(obj, "portal_type", "") != DEFAULT_STUDY_TYPE:
                continue
            try:
                container.manage_delObjects([child_id])
                logger.info("Removed obsolete default study '%s'", child_id)
            except Exception:
                if low_level_delete(child_id):
                    logger.info("Removed obsolete default study via low-level delete '%s'", child_id)
            cleanup_stale_entries(obj)

    def migrate_storage_time_duration(table):
        if table is None:
            return
        try:
            templates = table.objectValues("StabilityPlanTemplate")
        except Exception as exc:
            logger.warning(
                "Could not enumerate StabilityPlanTemplate objects in %s: %s",
                object_label(table),
                exc,
            )
            templates = []
        for obj in templates:
            try:
                current = getattr(obj, "storage_time", None)
                old = getattr(obj, "storage_duration_minutes", None)
                if isinstance(current, (int, long)) and current:
                    obj.storage_time = timedelta(minutes=int(current))
                if current is None and isinstance(old, (int, long)) and old:
                    obj.storage_time = timedelta(minutes=int(old))
            except Exception as exc:
                logger.warning(
                    "Could not migrate storage_time for %s: %s",
                    object_label(obj),
                    exc,
                )
                continue

    container = None
    for cid in _candidate_ids(MODULE_ID):
        container = portal.get(cid)
        if container is not None:
            break
    if container is None:
        with temporary_allow_type(portal, MODULE_TYPE):
            container = create_or_update(portal, MODULE_TYPE, MODULE_ID, MODULE_TITLE)
    else:
        recatalog(container)
        force_setup_like_permissions(container)
        update_security(container)

    if container is not None:
        for table_id, table_title, table_type in STATIC_TABLES:
            table = create_or_update(
                container, table_type, table_id, _table_title(table_title))
            if table_type == "StabilityPlanTemplates":
                apply_constraints(table, ("StabilityPlanTemplate",))
                migrate_storage_time_duration(table)
            if table_type == "StabilityPlans":
                apply_constraints(table, ("StabilityPlan",))
            if table_id == TABLE_ID_BY_LOGICAL["task_board"]:
                apply_constraints(table, ())
                try:
                    table.setLayout("task_board")
                    # Ensure it's not excluded from navigation
                    if getattr(table, "setExcludeFromNav", None):
                        table.setExcludeFromNav(False)
                    table.reindexObject(idxs=["excludeFromNav", "review_state"])
                    logger.info("Configured stability task board entry at '%s'", api.get_path(table))
                except Exception as exc:
                    logger.warning(
                        "Could not configure stability task board entry at '%s': %s",
                        object_label(table),
                        exc,
                    )

        # Default Stability Study is no longer used and should not appear in sidebar.
        delete_if_exists(container, DEFAULT_STUDY_ID)
        delete_default_studies(container)
        reorder_children(container, [item[0] for item in STATIC_TABLES])
        scrub_missing_children(container)

    setup_tool = api.get_senaite_setup()
    if setup_tool:
        folders = list(setup_tool.getSidebarFolders())
        actual_module_id = api.get_id(container) if container else MODULE_ID
        for obsolete_id in _candidate_ids(MODULE_ID):
            if obsolete_id != actual_module_id and obsolete_id in folders:
                folders.remove(obsolete_id)
        if actual_module_id not in folders:
            folders.append(actual_module_id)
            setup_tool.setSidebarFolders(tuple(folders))
        current_depth = getattr(
            setup_tool, "getSidebarNavigationDepth", lambda: None
        )()
        set_depth = getattr(setup_tool, "setSidebarNavigationDepth", None)
        if set_depth and (current_depth is None or current_depth < SIDEBAR_DEPTH):
            set_depth(SIDEBAR_DEPTH)


def uninstall_handler(context):
    """标准插件卸载入口。"""
    uninstall_file = "%s-uninstall.txt" % PROJECTNAME
    if context.readDataFile(uninstall_file) is None:
        return
    uninstall(context)


def uninstall(context):
    """Uninstall handler - 不删除业务数据，仅清理侧边栏注册信息
    """
    logger.info("MAITUX Stability Studies uninstall handler [BEGIN]")
    portal = api.get_portal()

    module_ids = list(_candidate_ids(MODULE_ID))

    # 移除侧边栏注册
    try:
        setup_tool = api.get_senaite_setup()
        if setup_tool:
            folders = list(setup_tool.getSidebarFolders())
            original = list(folders)
            folders = [folder_id for folder_id in folders if folder_id not in module_ids]
            if folders != original:
                setup_tool.setSidebarFolders(tuple(folders))
                logger.info(
                    "Removed stability folder ids from SENAITE sidebar folders: %s",
                    ", ".join(module_ids),
                )
    except Exception as exc:
        logger.warning(
            "Could not remove stability folder ids from sidebar folders: %s", exc
        )

    logger.info("MAITUX Stability Studies uninstall handler [DONE]")
