# -*- coding: utf-8 -*-

from bika.lims import api
from plone import api as ploneapi
from Products.CMFCore.utils import getToolByName
from Products.CMFPlone.interfaces import INonInstallable
from zope.interface import implementer

from maitux.hazardcategories import logger
from maitux.hazardcategories.config import PROJECTNAME
from maitux.hazardcategories.utils import parse_categories

from INNOCARE.arextension.defaults import (
    DEFAULT_HAZARD_CATEGORIES as DEFAULT_CATEGORIES,
)

from maitux.hazardcategories import _ as _hc
from INNOCARE.arextension.setuphandlers import (
    ensure_hazardcategory_data_synced as arextension_upsert,
    translate_with_fallback,
)

FOLDER_ID = "hazard_categories"
FOLDER_TITLE_MSG = _hc(u"HazardCategories Container",
                       default=u"Sample Properties")
FOLDER_TITLE = u"Sample Properties"
FOLDER_TYPE = "HazardCategories"
FTI_CONTAINER_LABEL_MSG = _hc(
    u"HazardCategories Container",
    default=u"Sample Properties",
)
FTI_ITEM_LABEL_MSG = _hc(
    u"HazardCategory Item",
    default=u"Sample Properties Item",
)
ITEM_TITLE_MSG = _hc(u"Sample Properties", default=u"Sample Properties")
DEFAULT_LAYOUT = "hazardcategories-controlpanel"
SIDEBAR_DEPTH = 2
PROFILE_ID = "profile-%s:default" % PROJECTNAME
LEGACY_CONFIGLET_ID = "maitux-hazardcategories"


@implementer(INonInstallable)
class HiddenProfiles(object):

    def getNonInstallableProfiles(self):
        return ["maitux.hazardcategories:uninstall"]


def unregister_legacy_configlet(portal):
    tool = getToolByName(portal, "portal_controlpanel", None)
    if tool is None:
        logger.warn("portal_controlpanel is missing, skip legacy cleanup")
        return
    try:
        tool.unregisterConfiglet(LEGACY_CONFIGLET_ID)
        logger.info("Removed legacy control panel entry '%s'", LEGACY_CONFIGLET_ID)
    except Exception:
        logger.info("Legacy control panel entry '%s' not registered",
                    LEGACY_CONFIGLET_ID)


def post_install(context):
    logger.info("maitux.hazardcategories post install [BEGIN]")
    portal = api.get_portal()
    run_install_steps(portal)
    logger.info("maitux.hazardcategories post install [DONE]")


def run_install_steps(portal):
    unregister_legacy_configlet(portal)
    setup_type_constraints()
    folder = setup_site_structure(portal)
    migrate_registry_items_into_folder(folder)
    ensure_hazardcategory_data_synced(folder)
    setup_permissions(folder)
    migrate_hazard_titles(portal)
    setup_sidebar()


def unregister_legacy_configlet(portal):
    """Drop the obsolete control panel entry for static dictionary data.

    maitux.hazardcategories is maintained through its folder/listing view and
    sidebar entry, not through Plone's add-on configlet area. Existing sites
    may still have the old configlet from previous profiles, so installation
    must actively unregister it.
    """
    tool = getToolByName(portal, "portal_controlpanel", None)
    if tool is None:
        return
    try:
        tool.unregisterConfiglet(CONFIGLET_ID)
        logger.info("Removed obsolete control panel entry '%s'", CONFIGLET_ID)
    except Exception:
        pass


def ensure_hazardcategory_data_synced(folder):
    return arextension_upsert(folder)


def migrate_hazard_titles(portal):
    """Set Hazard Categories folder + FTI titles to maitux.hazardcategories
    domain Messages, replacing legacy arextension-domain Messages or plain
    strings so runtime translation resolves via the package catalog.
    """
    logger.info("*** Migrate Hazard Categories titles (maitux.hazardcategories) ***")
    types_tool = api.get_tool("portal_types")
    item_msg = _hc(u"HazardCategory Item", default=u"Sample Properties Item")
    mapping = {
        FOLDER_TYPE: FOLDER_TITLE_MSG,
        "HazardCategory": item_msg,
    }
    updated = 0
    if types_tool is not None:
        for portal_type, msg in mapping.items():
            fti = getattr(types_tool, portal_type, None)
            if fti is None:
                continue
            try:
                fti._updateProperty("title", msg)
            except Exception:
                pass
            try:
                fti.manage_changeProperties(title=msg)
            except Exception:
                pass
            fti.title = msg
            try:
                fti._p_changed = 1
            except Exception:
                pass
            updated += 1
            logger.info("hazard: FTI %s title -> Message (maitux.hazardcategories)",
                        portal_type)
    folder = getattr(portal, FOLDER_ID, None)
    if folder is not None:
        try:
            folder.setTitle(FOLDER_TITLE_MSG)
            try:
                folder.reindexObject(idxs=["Title", "sortable_title"])
            except Exception:
                pass
            updated += 1
            logger.info("hazard: folder %s title -> Message (maitux.hazardcategories)",
                        FOLDER_ID)
        except Exception as exc:
            logger.warn("hazard: folder title update failed: %s", exc)
    return updated


def setup_type_constraints():
    logger.info("*** Setup Hazard Categories Type Constraints ***")
    types_tool = api.get_tool("portal_types")
    if types_tool is None:
        raise RuntimeError("portal_types tool not found")

    fti_folder = types_tool.getTypeInfo(FOLDER_TYPE)
    fti_item = types_tool.getTypeInfo("HazardCategory")
    if fti_folder is None or fti_item is None:
        try:
            setup_tool = api.get_tool("portal_setup")
            setup_tool.runImportStepFromProfile(PROFILE_ID, "typeinfo")
            logger.info("Ran 'typeinfo' import step from %s", PROFILE_ID)
            fti_folder = types_tool.getTypeInfo(FOLDER_TYPE)
            fti_item = types_tool.getTypeInfo("HazardCategory")
        except Exception as exc:
            logger.warn("typeinfo import failed: %s", exc)

    ensure_allowed_content_type(types_tool, "Plone Site", FOLDER_TYPE)

    hc_fti = types_tool.getTypeInfo(FOLDER_TYPE)
    if hc_fti is None:
        logger.warn("FTI '%s' not yet registered, allow_content_types skipped", FOLDER_TYPE)
    else:
        allowed = list(getattr(hc_fti, "allowed_content_types", ()) or ())
        if "HazardCategory" not in allowed:
            allowed = list(allowed) + ["HazardCategory"]
            hc_fti.manage_changeProperties(allowed_content_types=tuple(allowed))
            logger.info("Added 'HazardCategory' to allowed_content_types of '%s'", FOLDER_TYPE)


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


def _translate_msg(portal, msg):
    return translate_with_fallback(msg, context=portal)


def setup_site_structure(portal):
    logger.info("*** Setup Hazard Categories Site Structure ***")
    msgid = u"HazardCategories Container"
    default = u"Sample Properties"
    FOLDER_TITLE_MSG = _hc(msgid, default=default)
    with ploneapi.env.adopt_roles(["Manager"]):
        existing = portal.get(FOLDER_ID)
        if existing is not None:
            existing_type = getattr(existing, "portal_type", "")
            if existing_type == FOLDER_TYPE:
                logger.info("Skip existing folder '%s' (%s)", FOLDER_ID, FOLDER_TYPE)
                folder = existing
            else:
                logger.info(
                    "Existing '%s' is type '%s', replacing with '%s'",
                    FOLDER_ID, existing_type, FOLDER_TYPE)
                folder = _replace_with_hazardcategories_fti(portal, existing)
        else:
            folder = ploneapi.content.create(
                container=portal,
                type=FOLDER_TYPE,
                id=FOLDER_ID,
                title=FOLDER_TITLE_MSG,
            )
            logger.info("Created folder '%s' with type '%s'", FOLDER_ID, FOLDER_TYPE)

        current_layout = getattr(folder, "getLayout", lambda: None)()
        if current_layout != DEFAULT_LAYOUT:
            folder.setLayout(DEFAULT_LAYOUT)
            logger.info("Set layout of '%s' to '%s'", FOLDER_ID, DEFAULT_LAYOUT)
        else:
            logger.info("Skip layout update, current layout is '%s'", current_layout)

        return folder


def _replace_with_hazardcategories_fti(portal, existing):
    msgid = u"Hazard Categories Sample Properties"
    default = u"Sample Properties"
    FOLDER_TITLE_MSG = _hc(msgid, default=default)
    folder_title = getattr(existing, "Title", lambda: None)() or None
    legacy_id = "{}_legacy".format(FOLDER_ID)
    idx = 1
    while legacy_id in portal:
        legacy_id = "{}_legacy_{}".format(FOLDER_ID, idx)
        idx += 1

    try:
        portal.manage_renameObject(FOLDER_ID, legacy_id)
        logger.info("Renamed legacy folder to '%s'", legacy_id)
    except Exception as exc:
        logger.warn("Rename failed, using clipboard move fallback: %s", exc)
        cb = portal.manage_cutObjects([FOLDER_ID])
        try:
            from Products.CMFCore.utils import getToolByName
            mtool = getToolByName(portal, "portal_membership")
            home = mtool.getHomeFolder()
            if home is not None:
                home.manage_pasteObjects(cb)
            else:
                portal.manage_delObjects([FOLDER_ID])
        except Exception:
            portal.manage_delObjects([FOLDER_ID])

    folder = ploneapi.content.create(
        container=portal,
        type=FOLDER_TYPE,
        id=FOLDER_ID,
        title=FOLDER_TITLE_MSG,
    )
    logger.info("Created new '%s' with type '%s'", FOLDER_ID, FOLDER_TYPE)
    return folder


def migrate_registry_items_into_folder(folder):
    logger.info("*** Migrate Hazard Categories items from registry ***")
    child_ids = list(getattr(folder, "objectIds", lambda: [])())
    hazard_child_ids = [
        cid for cid in child_ids
        if getattr(folder[cid], "portal_type", "") == "HazardCategory"
    ] if child_ids else []

    if hazard_child_ids:
        logger.info(
            "Skip migration, already have %s HazardCategory child(ren)",
            len(hazard_child_ids))
        return

    from maitux.hazardcategories.utils import get_registry_value
    text_val = None
    try:
        text_val = get_registry_value()
    except Exception as exc:
        logger.warn("Failed to read old registry value: %s", exc)

    if not text_val:
        logger.warn("No registry value, falling back to DEFAULT_CATEGORIES")
        text_val = DEFAULT_CATEGORIES

    parsed = parse_categories(text_val)
    if not parsed:
        logger.info("No items to migrate")
        return

    with ploneapi.env.adopt_roles(["Manager"]):
        created = 0
        for cat in parsed:
            code = (cat.get("code") or u"").strip()
            if not code:
                continue
            name = (cat.get("name") or u"").strip()
            common = (cat.get("common") or u"").strip()
            pict = (cat.get("pictogram") or u"").strip()
            usage_scope = (cat.get("usage_scope") or u"both").strip()
            if usage_scope not in (u"both", u"reference", u"ar"):
                usage_scope = u"both"
            title = name or code
            obj = ploneapi.content.create(
                container=folder,
                type="HazardCategory",
                title=title,
                safe_id=False,
            )
            obj.code = code
            obj.name = name
            obj.common = common
            obj.pictogram = pict
            obj.usage_scope = usage_scope
            obj.reindexObject()
            created += 1
        logger.info("Migrated %s HazardCategory item(s) from registry", created)


def setup_permissions(folder):
    logger.info("*** Setup Hazard Categories Permissions ***")
    roles = ["LabClerk", "LabManager", "Manager", "Owner"]
    targets = [folder]
    for cid in list(getattr(folder, "objectIds", lambda: [])()):
        targets.append(folder[cid])

    for obj in targets:
        obj.manage_permission("View", roles=roles, acquire=0)
        obj.manage_permission(
            "Access contents information", roles=roles, acquire=0)
        obj.reindexObjectSecurity()
    logger.info("Updated permissions for %s object(s) under %s",
                len(targets), api.get_path(folder))


def setup_sidebar():
    logger.info("*** Setup Hazard Categories Sidebar ***")
    setup_tool = api.get_senaite_setup()
    if setup_tool is None:
        raise RuntimeError("SENAITE setup tool not found")

    folders = list(setup_tool.getSidebarFolders())
    if FOLDER_ID not in folders:
        folders.append(FOLDER_ID)
        setup_tool.setSidebarFolders(tuple(folders))
        logger.info("Added '%s' to SENAITE sidebar folders", FOLDER_ID)
    else:
        logger.info("Skip existing sidebar folder '%s'", FOLDER_ID)

    get_depth = getattr(setup_tool, "getSidebarNavigationDepth", None)
    set_depth = getattr(setup_tool, "setSidebarNavigationDepth", None)
    if callable(get_depth) and callable(set_depth):
        current = get_depth()
        if current is None or current < SIDEBAR_DEPTH:
            set_depth(SIDEBAR_DEPTH)
            logger.info("Set sidebar navigation depth to %s", SIDEBAR_DEPTH)
        else:
            logger.info("Skip sidebar depth update, current depth is %s", current)


def uninstall(context):
    logger.info("maitux.hazardcategories uninstall [BEGIN]")
    portal = api.get_portal()
    unregister_legacy_configlet(portal)

    setup_tool = api.get_senaite_setup()
    if setup_tool is None:
        raise RuntimeError("SENAITE setup tool not found")

    folders = list(setup_tool.getSidebarFolders())
    if FOLDER_ID in folders:
        folders.remove(FOLDER_ID)
        setup_tool.setSidebarFolders(tuple(folders))
        logger.info("Removed '%s' from SENAITE sidebar folders", FOLDER_ID)
    else:
        logger.info("Skip missing sidebar folder '%s'", FOLDER_ID)

    logger.info("maitux.hazardcategories uninstall [DONE]")
