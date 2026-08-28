# -*- coding: utf-8 -*-

import re

from bika.lims import api
from plone import api as ploneapi
from Products.CMFPlone.interfaces import INonInstallable
from zope.interface import implementer

from maitux.hazardcategories import logger
from maitux.hazardcategories import _ as _hc
from maitux.hazardcategories.config import (
    DEFAULT_CATEGORIES,
    LEGACY_HAZARD_EN_COMMON,
    PROJECTNAME,
)
from maitux.hazardcategories.translation import (
    _to_unicode,
    translate_with_fallback,
)
from maitux.hazardcategories.utils import (
    SCOPE_AR,
    SCOPE_BOTH,
    SCOPE_REFERENCE,
    parse_categories,
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


@implementer(INonInstallable)
class HiddenProfiles(object):

    def getNonInstallableProfiles(self):
        return ["maitux.hazardcategories:uninstall"]


def post_install(context):
    logger.info("maitux.hazardcategories post install [BEGIN]")
    portal = api.get_portal()
    run_install_steps(portal)
    logger.info("maitux.hazardcategories post install [DONE]")


def run_install_steps(portal):
    setup_type_constraints()
    folder = setup_site_structure(portal)
    migrate_registry_items_into_folder(folder)
    ensure_hazardcategory_data_synced(folder)
    ensure_setup_catalog_usage_scope_index(portal)
    ensure_hazardcategories_in_setup_catalog(portal)
    setup_permissions(folder)
    migrate_hazard_titles(portal)
    setup_sidebar()


def _split_categories_rows(text):
    rows = []
    if text is None:
        return rows
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    for raw in re.split(r"[\r\n]+", text):
        raw = raw.strip()
        if not raw:
            continue
        parts = raw.split("|")
        if len(parts) < 2:
            continue
        row = [p.strip() for p in parts]
        while len(row) < 4:
            row.append(u"")
        rows.append(row[:4])
    return rows


def default_hazard_categories_list():
    rows = _split_categories_rows(DEFAULT_CATEGORIES)
    result = []
    for r in rows:
        result.append({
            "code": r[0],
            "name": r[1],
            "common": r[2],
            "pictogram": r[3],
            "usage_scope": SCOPE_BOTH,
        })
    return result


def ensure_hazardcategory_data_synced(folder):
    logger.info("*** Upsert HazardCategory seed data (maitux.hazardcategories, code-based) ***")
    expected = default_hazard_categories_list() or []
    expected_by_code = {}
    for cat in expected:
        c = (cat.get("code") or u"").strip()
        if c:
            expected_by_code[c] = cat
    if not expected:
        logger.warn("No seed categories available, skip upsert")
        return (0, 0, 0)

    existing = {}
    if folder is not None:
        for (cid, obj) in list(getattr(folder, "contentItems", lambda: [])()):
            if api.get_portal_type(obj) != "HazardCategory":
                continue
            code = (getattr(obj, "code", None) or u"").strip()
            if not code:
                continue
            existing[code] = obj

    def _sanitize_title(text):
        if text is None:
            return u""
        t = _to_unicode(text)
        for ch in (u"/", u"\\", u"(", u")", u"[", u"]", u"{", u"}",
                   u"|", u"!", u"?", u"#", u"<", u">", u"*", u":", u"\"",
                   u"'", u"~", u"`", u"^", u"%", u"$", u"@", u"&"):
            t = t.replace(ch, u"")
        # collapse spaces
        while u"  " in t:
            t = t.replace(u"  ", u" ")
        return t.strip()

    created = 0
    updated = 0
    untouched = 0

    with ploneapi.env.adopt_roles(["Manager"]):
        for cat in expected:
            code = (cat.get("code") or u"").strip()
            if not code:
                continue
            name = (cat.get("name") or u"").strip()
            common = (cat.get("common") or u"").strip()
            pict = (cat.get("pictogram") or u"").strip()
            usage_scope = (cat.get("usage_scope") or SCOPE_BOTH).strip()
            if usage_scope not in (SCOPE_BOTH, SCOPE_REFERENCE, SCOPE_AR):
                usage_scope = SCOPE_BOTH

            expected_title_raw = (common or name or code)
            expected_title = _sanitize_title(u"%s %s" % (code, expected_title_raw))

            obj = existing.get(code)
            if obj is None:
                try:
                    obj = ploneapi.content.create(
                        container=folder,
                        type="HazardCategory",
                        title=expected_title,
                        safe_id=False,
                    )
                    obj.code = code
                    obj.name = name
                    obj.common = common
                    obj.pictogram = pict
                    obj.usage_scope = usage_scope
                    obj.reindexObject()
                    created += 1
                    logger.info("  INSERT code=%s title=%s common=%s",
                                code, expected_title, common)
                except Exception as exc:
                    logger.warn("  INSERT FAIL code=%s exc=%s", code, exc)
                continue

            def _g(a):
                return (getattr(obj, a, None) or u"").strip()

            cur_common = _g("common")
            cur_pict = _g("pictogram")
            cur_scope = _g("usage_scope") or SCOPE_BOTH
            cur_name = _g("name")
            cur_title_raw = getattr(obj, "Title", lambda: u"")() or u""
            cur_title_uni = _to_unicode(cur_title_raw)
            legacy_en = LEGACY_HAZARD_EN_COMMON.get(code)

            dirty = False
            need_common = False
            if not cur_common:
                need_common = True
            elif common and legacy_en and cur_common == legacy_en:
                need_common = True
                logger.info("  UPDATE code=%s common (legacy default en) %r -> %r",
                            code, cur_common, common)
            if need_common and common:
                obj.common = common
                dirty = True
            if not cur_pict and pict:
                obj.pictogram = pict
                dirty = True
                logger.info("  UPDATE code=%s pictogram (empty) -> %s", code, pict)
            if usage_scope and (
                cur_scope not in (SCOPE_BOTH, SCOPE_REFERENCE, SCOPE_AR)
                or (not _g("usage_scope"))
            ):
                obj.usage_scope = usage_scope
                dirty = True
            if not cur_name and name:
                obj.name = name
                dirty = True
            # Title sync: never overwrite user custom titles
            if expected_title:
                allowed = (not cur_title_uni,
                           cur_title_uni == _sanitize_title(u"%s %s" % (code, name)),
                           cur_title_uni == _sanitize_title(u"%s %s" % (code, common)),
                           cur_title_uni == _sanitize_title(name),
                           cur_title_uni == _sanitize_title(common),
                           cur_title_uni == code)
                if any(allowed) and cur_title_uni != expected_title:
                    try:
                        obj.setTitle(expected_title)
                        logger.info("  UPDATE code=%s title %r -> %r",
                                    code, cur_title_uni, expected_title)
                        dirty = True
                    except Exception as exc:
                        logger.warn("  UPDATE title code=%s exc=%s", code, exc)

            if dirty:
                try:
                    obj.reindexObject(idxs=[
                        "Title", "sortable_title", "SearchableText"])
                    updated += 1
                except Exception as exc:
                    logger.warn("  REINDEX FAIL code=%s exc=%s", code, exc)
            else:
                untouched += 1

    logger.info("Upsert done: created=%d updated=%d untouched=%d (existing=%d)",
                created, updated, untouched, len(existing))
    return (created, updated, untouched)


def ensure_setup_catalog_usage_scope_index(portal):
    sc = None
    try:
        sc = api.get_tool("senaite_catalog_setup")
    except Exception:
        sc = getattr(portal, "senaite_catalog_setup", None)
    if sc is None:
        return 0
    changed = 0
    try:
        idx = None
        try:
            idx = sc._catalog.getIndex("usage_scope")
        except Exception:
            idx = None
        # The index is only useful if it is a KeywordIndex whose attr
        # resolves the ``usage_scope`` field/indexer; otherwise rebuild it
        idx_attr = None
        if idx is not None:
            try:
                idx_attr = getattr(idx, "attr", None)
            except Exception:
                idx_attr = None
        if idx is not None and (
                idx.__class__.__name__ != "KeywordIndex" or
                idx_attr != "usage_scope"):
            try:
                sc.delIndex("usage_scope")
            except Exception:
                pass
            idx = None
        if idx is None and "usage_scope" not in sc.indexes():
            # NOTE: the KeywordIndex MUST be created with attr="usage_scope",
            # otherwise ``getattr(obj, None)`` raises inside index_object and
            # the index silently stays empty (ReferenceWidget -> no candidates)
            sc.addIndex("usage_scope", "KeywordIndex",
                        {"attr": "usage_scope"})
            changed += 1
    except Exception:
        pass
    try:
        if "usage_scope" not in sc.schema():
            sc.addColumn("usage_scope")
            changed += 1
    except Exception:
        pass
    if changed:
        try:
            sc.reindexIndex("usage_scope", portal.REQUEST)
        except Exception:
            try:
                sc.refreshCatalog()
            except Exception:
                pass
    # Always re-index the HazardCategory objects directly on this catalog.
    # The CMFCore index queue only processes ``portal_catalog``, so the
    # queue-based ``reindexObject()`` never reaches the setup catalog and
    # the ``usage_scope`` / ``allowedRolesAndUsers`` indexes stay empty
    # unless we write them directly here.
    try:
        folder = getattr(portal, FOLDER_ID, None)
        if folder is not None:
            for cid, obj in folder.contentItems():
                if getattr(obj, "portal_type", "") == "HazardCategory":
                    try:
                        sc._reindexObject(
                            obj,
                            idxs=["usage_scope", "allowedRolesAndUsers"])
                    except Exception:
                        pass
    except Exception:
        pass
    return changed


def ensure_hazardcategories_in_setup_catalog(portal):
    """把 hazard_categories 容器及全部 HazardCategory 子项补进
    senaite_catalog_setup / uid_catalog，供 sidebar 二级菜单和
    ReferenceWidget 正确显示标题。幂等：重复执行无副作用。
    """
    folder = None
    try:
        folder = portal._getOb("hazard_categories", None)
    except Exception:
        folder = getattr(portal, "hazard_categories", None)
    if folder is None:
        return 0
    targets = [folder]
    try:
        items = list(getattr(folder, "contentItems", lambda: [])())
    except Exception:
        items = []
    for cid, obj in items:
        if api.get_portal_type(obj) == "HazardCategory":
            targets.append(obj)
    done = 0
    for obj in targets:
        path = "/".join(obj.getPhysicalPath())
        try:
            for tool_name in ("senaite_catalog_setup", "uid_catalog"):
                cat = None
                try:
                    cat = api.get_tool(tool_name)
                except Exception:
                    cat = getattr(portal, tool_name, None)
                if cat is None:
                    continue
                cat.catalog_object(obj, path)
            done += 1
        except Exception as exc:
            logger.warn("ensure_hazardcategories_in_setup_catalog FAIL %s: %s",
                        getattr(obj, "getId", lambda: "?")(), exc)
    if done:
        logger.info("ensure_hazardcategories_in_setup_catalog cataloged %d", done)
    return done


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
