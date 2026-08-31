# -*- coding: utf-8 -*-
from bika.lims import api
from plone import api as ploneapi
from Products.CMFPlone.interfaces import INonInstallable
from senaite.core import logger
from zope.interface import implementer

from maitux.stock import _
from maitux.stock.config import PROJECTNAME
from maitux.stock.stockbatchexpiry import REVIEW_STATE_ACTIVE
from maitux.stock.stockbatchexpiry import REVIEW_STATE_DESTROYED
from maitux.stock.stockbatchexpiry import expire_batch
from maitux.stock.stockbatchexpiry import is_due_for_expiry
from maitux.stock.stockbatchexpiry import set_status_value

STOCK_MANAGER_ID = "stockmanager"
STOCK_MANAGER_TITLE = _(u"Stockinventory", default=u"Stockinventory")
DYNAMIC_SECTION_ID = "stock_dynamic"
STOCK_FOLDER_ID = "stock"
STOCK_FOLDER_TITLE = _(u"Stock Item", default=u"Stock Item")
STOCK_UNITS_ID = "stock_units"
STOCK_TYPES_ID = "stock_types"
PURCHASE_ORDERS_ID = "purchase_orders"
STOCK_BATCHES_ID = "stock_batches"
LOW_STOCK_ID = "low_stock"
LOW_STOCK_TITLE = _(u"Low Quantity", default=u"Low Quantity")
SIDEBAR_DEPTH = 2

STOCK_CHILDREN = (
    (STOCK_UNITS_ID, "StockUnits", _(u"Units", default=u"Units")),
    (STOCK_TYPES_ID, "StockTypes", _(u"Stock Types", default=u"Stock Types")),
    (PURCHASE_ORDERS_ID, "StockPurchaseOrders", _(u"Purchase Orders", default=u"Purchase Orders")),
    (STOCK_BATCHES_ID, "StockBatches", _(u"Stock Batches", default=u"Stock Batches")),
)


@implementer(INonInstallable)
class HiddenProfiles(object):
    """隐藏卸载 profile，保持插件入口与标准 Add-on 一致。"""

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

    logger.info("MAITUX STOCK setup handler [BEGIN]")
    portal = context.getSite()
    run_install_steps(portal)
    logger.info("MAITUX STOCK setup handler [DONE]")


def setup_stock_content(context):
    """兼容旧入口，统一委托到标准插件安装入口。"""
    setup_handler(context)


def run_install_steps(portal):
    """按官方安装器风格拆分步骤，逐步执行并保留完整日志。"""
    setup_type_constraints()
    stock_manager = setup_site_structure(portal)
    setup_permissions(stock_manager)
    setup_sidebar()
    setup_workflows()
    reindex_stock_structure(stock_manager)


def setup_type_constraints():
    logger.info("*** Setup Stock Type Constraints ***")
    types_tool = api.get_tool("portal_types")
    if types_tool is None:
        raise RuntimeError("portal_types tool not found")

    ensure_allowed_content_type(types_tool, "Plone Site", "StockManager")
    ensure_allowed_content_type(types_tool, "StockManager", "LowStockSection")


def ensure_allowed_content_type(types_tool, type_name, allowed_type):
    fti = types_tool.getTypeInfo(type_name)
    if fti is None:
        raise RuntimeError("FTI '{}' not found".format(type_name))

    allowed = list(getattr(fti, "allowed_content_types", ()) or ())
    if allowed_type in allowed:
        logger.info("Skip allowed_content_types update for '%s' -> '%s'", type_name, allowed_type)
        return

    allowed.append(allowed_type)
    fti.manage_changeProperties(allowed_content_types=tuple(allowed))
    logger.info("Added '%s' to allowed_content_types of '%s'", allowed_type, type_name)


def setup_site_structure(portal):
    logger.info("*** Setup Stock Site Structure ***")
    with ploneapi.env.adopt_roles(["Manager"]):
        migrate_legacy_stock_root_from_setup(portal)
        stock_manager = ensure_content(
            portal, "StockManager", STOCK_MANAGER_ID, STOCK_MANAGER_TITLE)
        remove_dynamic_section(stock_manager)
        stock_folder = ensure_stock_folder(stock_manager)
        migrate_legacy_root_stock_folder(portal, stock_folder)
        move_root_stock_items_into_folder(stock_manager, stock_folder)

        for child_id, portal_type, title in STOCK_CHILDREN:
            ensure_content(stock_manager, portal_type, child_id, title)

        ensure_low_stock_section(stock_manager)
        return stock_manager


def migrate_legacy_stock_root_from_setup(portal):
    logger.info("*** Migrate Legacy Root From bika_setup ***")
    bika_setup = api.get_bika_setup()
    if bika_setup is None or STOCK_FOLDER_ID not in bika_setup:
        logger.info("Skip legacy migration from bika_setup")
        return

    if STOCK_FOLDER_ID in portal:
        bika_setup.manage_delObjects([STOCK_FOLDER_ID])
        logger.info("Removed legacy '%s' from bika_setup because portal root already has it", STOCK_FOLDER_ID)
        return

    clipboard = bika_setup.manage_cutObjects([STOCK_FOLDER_ID])
    portal.manage_pasteObjects(clipboard)
    logger.info("Moved legacy '%s' from bika_setup to portal root", STOCK_FOLDER_ID)


def ensure_content(container, portal_type, obj_id, title):
    """先检查再创建，避免依赖 try/except 做幂等。"""
    if obj_id in container:
        obj = container[obj_id]
        existing_type = getattr(obj, "portal_type", "")
        if existing_type != portal_type:
            raise RuntimeError(
                "Expected '{}' at '{}', got '{}'".format(
                    portal_type, api.get_path(obj), existing_type))
        ensure_title(obj, title)
        logger.info("Skip existing %s", api.get_path(obj))
        return obj

    ploneapi.content.create(
        container=container,
        type=portal_type,
        id=obj_id,
        title=title,
    )
    obj = container[obj_id]
    logger.info("Created %s", api.get_path(obj))
    return obj


def ensure_title(obj, title):
    if not getattr(obj, "Title", None):
        return
    if obj.Title() == title:
        return
    obj.setTitle(title)
    logger.info("Updated title for %s", api.get_path(obj))


def remove_dynamic_section(stock_manager):
    logger.info("*** Remove Dynamic Section ***")
    if DYNAMIC_SECTION_ID not in stock_manager:
        logger.info("Skip missing '%s' section", DYNAMIC_SECTION_ID)
        return
    stock_manager.manage_delObjects([DYNAMIC_SECTION_ID])
    logger.info("Removed '%s' section from stock manager", DYNAMIC_SECTION_ID)


def ensure_stock_folder(stock_manager):
    logger.info("*** Ensure Stock Folder ***")
    if STOCK_FOLDER_ID not in stock_manager:
        return ensure_content(
            stock_manager, "StockFolder", STOCK_FOLDER_ID, STOCK_FOLDER_TITLE)

    stock_folder = stock_manager[STOCK_FOLDER_ID]
    if getattr(stock_folder, "portal_type", "") != "StockFolder":
        raise RuntimeError("Existing '{}' is not a StockFolder".format(STOCK_FOLDER_ID))

    if api.get_uid(stock_folder):
        ensure_title(stock_folder, STOCK_FOLDER_TITLE)
        logger.info("Skip existing %s", api.get_path(stock_folder))
        return stock_folder

    # 历史坏数据可能没有 UID，这里显式重建并迁移子对象。
    legacy_id = get_unique_legacy_id(stock_manager, STOCK_FOLDER_ID)
    stock_manager.manage_renameObject(STOCK_FOLDER_ID, legacy_id)
    logger.info("Renamed broken stock folder to '%s'", legacy_id)
    stock_folder = ensure_content(
        stock_manager, "StockFolder", STOCK_FOLDER_ID, STOCK_FOLDER_TITLE)
    move_children(stock_manager[legacy_id], stock_folder)
    stock_manager.manage_delObjects([legacy_id])
    logger.info("Rebuilt stock folder '%s'", api.get_path(stock_folder))
    return stock_folder


def get_unique_legacy_id(container, base_id):
    legacy_id = "{}_legacy".format(base_id)
    index = 1
    while legacy_id in container:
        legacy_id = "{}_legacy_{}".format(base_id, index)
        index += 1
    return legacy_id


def move_children(source, target):
    child_ids = list(getattr(source, "objectIds", lambda: [])())
    if not child_ids:
        logger.info("Skip empty move from %s", api.get_path(source))
        return

    clipboard = source.manage_cutObjects(child_ids)
    target.manage_pasteObjects(clipboard)
    logger.info("Moved %s child object(s) from %s to %s",
                len(child_ids), api.get_path(source), api.get_path(target))


def migrate_legacy_root_stock_folder(portal, stock_folder):
    logger.info("*** Migrate Legacy Portal Stock Folder ***")
    if STOCK_FOLDER_ID not in portal:
        logger.info("Skip missing legacy portal root '%s'", STOCK_FOLDER_ID)
        return

    legacy = portal[STOCK_FOLDER_ID]
    if getattr(legacy, "portal_type", "") != "StockFolder":
        raise RuntimeError("Legacy portal root '{}' is not a StockFolder".format(STOCK_FOLDER_ID))

    move_children(legacy, stock_folder)
    portal.manage_delObjects([STOCK_FOLDER_ID])
    logger.info("Removed migrated legacy portal root '%s'", STOCK_FOLDER_ID)


def move_root_stock_items_into_folder(stock_manager, stock_folder):
    logger.info("*** Move Root Stock Items ***")
    moved = 0
    for obj_id in list(getattr(stock_manager, "objectIds", lambda: [])()):
        if obj_id == STOCK_FOLDER_ID:
            continue
        obj = stock_manager.get(obj_id)
        if getattr(obj, "portal_type", "") != "Stock":
            continue
        clipboard = stock_manager.manage_cutObjects([obj_id])
        stock_folder.manage_pasteObjects(clipboard)
        moved += 1

    if moved:
        logger.info("Moved %s stock item(s) into %s", moved, api.get_path(stock_folder))
    else:
        logger.info("Skip root stock item migration")


def ensure_low_stock_section(stock_manager):
    logger.info("*** Ensure Low Stock Section ***")
    if LOW_STOCK_ID in stock_manager:
        existing = stock_manager[LOW_STOCK_ID]
        if getattr(existing, "portal_type", "") != "LowStockSection":
            stock_manager.manage_delObjects([LOW_STOCK_ID])
            logger.info("Removed incompatible '%s' before recreation", LOW_STOCK_ID)

    ensure_content(
        stock_manager, "LowStockSection", LOW_STOCK_ID, LOW_STOCK_TITLE)


def setup_permissions(stock_manager):
    logger.info("*** Setup Stock Permissions ***")
    roles = ["LabClerk", "LabManager", "Manager", "Owner"]
    targets = [
        stock_manager,
        stock_manager.get(STOCK_FOLDER_ID),
        stock_manager.get(STOCK_UNITS_ID),
        stock_manager.get(STOCK_TYPES_ID),
        stock_manager.get(PURCHASE_ORDERS_ID),
        stock_manager.get(STOCK_BATCHES_ID),
        stock_manager.get(LOW_STOCK_ID),
    ]

    for obj in filter(None, targets):
        obj.manage_permission("View", roles=roles, acquire=0)
        obj.manage_permission("Access contents information", roles=roles, acquire=0)
        obj.reindexObjectSecurity()
        logger.info("Updated permissions for %s", api.get_path(obj))


def setup_sidebar():
    logger.info("*** Setup Stock Sidebar ***")
    setup_tool = api.get_senaite_setup()
    if setup_tool is None:
        raise RuntimeError("SENAITE setup tool not found")

    folders = list(setup_tool.getSidebarFolders())
    if STOCK_MANAGER_ID not in folders:
        folders.append(STOCK_MANAGER_ID)
        setup_tool.setSidebarFolders(tuple(folders))
        logger.info("Added '%s' to SENAITE sidebar folders", STOCK_MANAGER_ID)
    else:
        logger.info("Skip existing sidebar folder '%s'", STOCK_MANAGER_ID)

    get_depth = getattr(setup_tool, "getSidebarNavigationDepth", None)
    set_depth = getattr(setup_tool, "setSidebarNavigationDepth", None)
    if callable(get_depth) and callable(set_depth):
        current = get_depth()
        if current is None or current < SIDEBAR_DEPTH:
            set_depth(SIDEBAR_DEPTH)
            logger.info("Set sidebar navigation depth to %s", SIDEBAR_DEPTH)
        else:
            logger.info("Skip sidebar depth update, current depth is %s", current)


def setup_workflows():
    logger.info("*** Setup StockBatch Workflow ***")
    workflow_tool = api.get_tool("portal_workflow")
    if workflow_tool is None:
        raise RuntimeError("portal_workflow tool not found")

    workflow_tool.setChainForPortalTypes(
        ("StockBatch",), ("senaite_stockbatch_workflow",))
    logger.info("Bound 'senaite_stockbatch_workflow' to 'StockBatch'")

    # 兼容当前 SENAITE/Plone 栈：角色映射更新应针对工作流定义或具体对象，
    # 不能对 portal_workflow 工具使用 portal_type 关键字参数。
    workflow_definition = workflow_tool.getWorkflowById(
        "senaite_stockbatch_workflow")

    catalog = api.get_tool("portal_catalog")
    brains = catalog(portal_type="StockBatch") if catalog else []
    synced_destroyed = 0
    synced_expired = 0
    rolemap_updated = 0
    for brain in brains:
        batch = brain.getObject()
        if not api.is_object(batch):
            continue
        if workflow_definition is not None:
            workflow_definition.updateRoleMappingsFor(batch)
            rolemap_updated += 1

        review_state = api.get_review_status(batch) or ""
        status_value = getattr(batch, "status", "") or ""

        if review_state == REVIEW_STATE_DESTROYED:
            if set_status_value(batch, REVIEW_STATE_DESTROYED):
                batch.reindexObject()
            continue

        if status_value == REVIEW_STATE_DESTROYED:
            workflow_tool.doActionFor(batch, "destroy")
            set_status_value(batch, REVIEW_STATE_DESTROYED)
            batch.reindexObject()
            synced_destroyed += 1
            continue

        if is_due_for_expiry(batch):
            if expire_batch(
                batch,
                workflow_tool=workflow_tool,
                operator=u"system",
                remarks=u"Auto expired during workflow setup",
                reindex=True,
            ):
                synced_expired += 1
                continue

        if review_state == REVIEW_STATE_ACTIVE and set_status_value(batch, REVIEW_STATE_ACTIVE):
            batch.reindexObject()

    logger.info("Updated workflow role mappings for %s StockBatch object(s)",
                rolemap_updated)
    logger.info("Synced destroyed workflow state for %s StockBatch object(s)", synced_destroyed)
    logger.info("Synced expired workflow state for %s StockBatch object(s)", synced_expired)


def reindex_stock_structure(stock_manager):
    logger.info("*** Reindex Stock Structure ***")
    targets = [
        stock_manager,
        stock_manager.get(STOCK_FOLDER_ID),
        stock_manager.get(STOCK_UNITS_ID),
        stock_manager.get(STOCK_TYPES_ID),
        stock_manager.get(PURCHASE_ORDERS_ID),
        stock_manager.get(STOCK_BATCHES_ID),
        stock_manager.get(LOW_STOCK_ID),
    ]

    for obj in filter(None, targets):
        obj.reindexObject()
        logger.info("Reindexed %s", api.get_path(obj))


def uninstall_handler(context):
    """标准插件卸载入口，不删除业务数据，仅清理注册信息。"""
    uninstall_file = "%s-uninstall.txt" % PROJECTNAME
    if context.readDataFile(uninstall_file) is None:
        return

    logger.info("MAITUX STOCK uninstall handler [BEGIN]")

    setup_tool = api.get_senaite_setup()
    if setup_tool is None:
        raise RuntimeError("SENAITE setup tool not found")

    folders = list(setup_tool.getSidebarFolders())
    if STOCK_MANAGER_ID in folders:
        folders.remove(STOCK_MANAGER_ID)
        setup_tool.setSidebarFolders(tuple(folders))
        logger.info("Removed '%s' from SENAITE sidebar folders", STOCK_MANAGER_ID)
    else:
        logger.info("Skip missing sidebar folder '%s'", STOCK_MANAGER_ID)

    logger.info("MAITUX STOCK uninstall handler [DONE]")


def uninstall(context):
    """兼容旧卸载入口，统一委托到标准插件卸载入口。"""
    uninstall_handler(context)

