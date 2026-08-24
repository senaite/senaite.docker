# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import logging
import os
import re
import time

from bika.lims import api as bapi

import plone.api as ploneapi
from Products.CMFCore import permissions

from INNOCARE.arextension import _, AREXTENSION_DOMAIN, logger

from INNOCARE.arextension.defaults import (
    DEFAULT_HAZARD_CATEGORIES,
    LEGACY_HAZARD_EN_COMMON,
    HAZARD_SCOPE_BOTH,
    HAZARD_SCOPE_REFERENCE,
    HAZARD_SCOPE_AR,
)


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
    rows = _split_categories_rows(DEFAULT_HAZARD_CATEGORIES)
    result = []
    for r in rows:
        result.append({
            "code": r[0],
            "name": r[1],
            "common": r[2],
            "pictogram": r[3],
            "usage_scope": HAZARD_SCOPE_BOTH,
        })
    return result


def translate_with_fallback(msg, context=None, languages=None,
                           domain=None):
    if msg is None:
        return u""
    msgid, _, _ = _msg_accessors(msg)
    try:
        default = _msg_accessors(msg)[2]
    except Exception:
        default = u""
    default = default or u""
    if languages is None:
        languages = (None, "zh_CN", "zh-cn", "zh", "en")
    if domain is None:
        domain = AREXTENSION_DOMAIN
    try:
        from zope.i18n import translate as zt
    except Exception:
        return _to_unicode(default) or _to_unicode(msg)

    result = None
    try:
        result = zt(msg, context=context, domain=domain)
    except Exception:
        result = None
    result_uni = _to_unicode(result) if result else u""
    default_uni = _to_unicode(default)
    msgid_uni = _to_unicode(msgid)
    if result_uni and result_uni != default_uni and result_uni != msgid_uni:
        return result_uni
    for lang in languages:
        try:
            if lang is None:
                candidate = zt(msg, context=context, domain=domain)
            else:
                candidate = zt(msg, target_language=lang,
                                context=context, domain=domain)
        except Exception:
            candidate = None
        cand_uni = _to_unicode(candidate) if candidate else u""
        if cand_uni and cand_uni != default_uni and cand_uni != msgid_uni:
            return cand_uni
    return result_uni or default_uni or _to_unicode(msg)


def _to_unicode(text):
    if text is None:
        return u""
    if isinstance(text, bytes):
        try:
            return text.decode("utf-8")
        except Exception:
            try:
                return text.decode("utf-8", "ignore")
            except Exception:
                return u""
    return unicode(text)


def _to_bytes(text):
    if isinstance(text, unicode):
        return text.encode("utf-8")
    return text


def ensure_fti_titles(portal, types_tool, mapping):
    logger.info("*** ensure_fti_titles (arextension) count=%d (legacy: no-op, migrated) ***", len(mapping))
    logger.info("  ensure_fti_titles is now a legacy stub; use migrate_runtime_titles instead.")
    return 0


def ensure_hazardcategory_data_synced(folder):
    logger.info("*** Upsert HazardCategory seed data (arextension, code-based) ***")
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
            if bapi.get_portal_type(obj) != "HazardCategory":
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
            usage_scope = (cat.get("usage_scope") or HAZARD_SCOPE_BOTH).strip()
            if usage_scope not in (HAZARD_SCOPE_BOTH, HAZARD_SCOPE_REFERENCE,
                                   HAZARD_SCOPE_AR):
                usage_scope = HAZARD_SCOPE_BOTH

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
            cur_scope = _g("usage_scope") or HAZARD_SCOPE_BOTH
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
                cur_scope not in (HAZARD_SCOPE_BOTH, HAZARD_SCOPE_REFERENCE,
                                  HAZARD_SCOPE_AR)
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
        sc = bapi.get_tool("senaite_catalog_setup")
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
        if idx is not None and idx.__class__.__name__ != "KeywordIndex":
            try:
                sc.delIndex("usage_scope")
            except Exception:
                pass
            idx = None
        if idx is None and "usage_scope" not in sc.indexes():
            sc.addIndex("usage_scope", "KeywordIndex")
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
        if bapi.get_portal_type(obj) == "HazardCategory":
            targets.append(obj)
    done = 0
    for obj in targets:
        path = "/".join(obj.getPhysicalPath())
        try:
            for tool_name in ("senaite_catalog_setup", "uid_catalog"):
                cat = None
                try:
                    cat = bapi.get_tool(tool_name)
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


def ensure_sample_catalog_projectno_index(portal):
    """Idempotently add the ``ProjectNo`` index to the sample catalog and
    (re)index existing Analysis Requests so the Project AR listing
    (``<project>/analysisrequests``) can query ARs by linked Project UID.

    The AR ``ProjectNo`` extension field stores the linked Project UID as a
    plain string attribute on the object, so a plain FieldIndex is enough.
    Existing ARs are re-cataloged with ``catalog_object`` (idempotent), which
    also repairs sites whose sample catalog was never populated.
    """
    sc = None
    try:
        sc = bapi.get_tool("senaite_catalog_sample")
    except Exception:
        sc = getattr(portal, "senaite_catalog_sample", None)
    if sc is None:
        logger.warn("ensure_sample_catalog_projectno_index: "
                    "senaite_catalog_sample not found, skipped")
        return
    try:
        from senaite.core.api.catalog import add_index as _add_index
        from senaite.core.api.catalog import del_index as _del_index
        current = None
        if "ProjectNo" in sc.indexes():
            try:
                current = sc._catalog.getIndex("ProjectNo")
            except Exception:
                current = None
        attrs = getattr(current, "indexed_attrs", None) if current else None
        if current is not None and attrs == ["ProjectNo"]:
            pass  # index already present and correctly configured
        else:
            if current is not None:
                try:
                    _del_index(sc, "ProjectNo")
                except Exception:
                    pass
            _add_index(sc, "ProjectNo", "FieldIndex",
                       indexed_attrs="ProjectNo")
            logger.info("Added 'ProjectNo' FieldIndex to "
                        "senaite_catalog_sample")
    except Exception as exc:
        logger.warn("ensure_sample_catalog_projectno_index: "
                    "addIndex failed: %s", exc)
        return
    uc = None
    try:
        uc = bapi.get_tool("uid_catalog")
    except Exception:
        uc = getattr(portal, "uid_catalog", None)
    if uc is None:
        logger.warn("ensure_sample_catalog_projectno_index: "
                    "uid_catalog not found, skipped reindex")
        return
    count = 0
    failed = 0
    try:
        brains = list(uc(portal_type="AnalysisRequest"))
    except Exception as exc:
        logger.warn("ensure_sample_catalog_projectno_index: "
                    "uid_catalog query failed: %s", exc)
        return
    for brain in brains:
        try:
            obj = brain.getObject()
        except Exception:
            failed += 1
            continue
        try:
            path = "/".join(obj.getPhysicalPath())
            if isinstance(path, unicode):
                # ZCatalog requires a byte string (Py2 str) as the object uid
                path = path.encode("utf-8")
            sc.catalog_object(obj, path)
            count += 1
        except Exception as exc:
            failed += 1
            logger.warn("ensure_sample_catalog_projectno_index: "
                        "catalog_object %s failed: %s",
                        getattr(obj, "getId", lambda: u"?")(), exc)
    logger.info("ensure_sample_catalog_projectno_index: indexed %d ARs "
                "(failed=%d) into senaite_catalog_sample", count, failed)


def post_install_setup(context):
    logger.info("*** INNOCARE.arextension post_install_setup begin ***")
    portal = bapi.get_portal()
    logger.info("  portal=%r language=%r", portal.id,
                getattr(portal, "language", None))
    try:
        migrate_runtime_titles(portal)
    except Exception as exc:
        logger.warn("migrate_runtime_titles failed: %s", exc)
    try:
        hc_folder = portal._getOb("hazard_categories", None)
        if hc_folder is not None:
            ensure_hazardcategory_data_synced(hc_folder)
    except Exception as exc:
        logger.warn("ensure_hazardcategory_data_synced failed: %s", exc)
    try:
        ensure_setup_catalog_usage_scope_index(portal)
    except Exception as exc:
        logger.warn("ensure_setup_catalog_usage_scope_index failed: %s", exc)
    try:
        ensure_hazardcategories_in_setup_catalog(portal)
    except Exception as exc:
        logger.warn("ensure_hazardcategories_in_setup_catalog failed: %s", exc)
    try:
        ensure_sample_catalog_projectno_index(portal)
    except Exception as exc:
        logger.warn("ensure_sample_catalog_projectno_index failed: %s", exc)
    logger.info("*** INNOCARE.arextension post_install_setup done ***")


FOLDER_TITLE_MESSAGES = {
    # Folder titles are owned by the add-on that creates them
    # (maitux.projects -> "projects", maitux.hazardcategories ->
    # "hazard_categories"). This registry is intentionally empty.
}

FTI_TITLE_MESSAGES = {
    # FTI titles are owned by the add-on that registers the content types.
}


def _get_folder_expected_title(folder_id):
    builder = FOLDER_TITLE_MESSAGES.get(folder_id)
    if builder is None:
        return None
    try:
        return builder()
    except Exception:
        return None


def _get_fti_expected_title(portal_type):
    builder = FTI_TITLE_MESSAGES.get(portal_type)
    if builder is None:
        return None
    try:
        return builder()
    except Exception:
        return None


def _msg_accessors(obj):
    if obj is None:
        return (None, None, None)
    if "Message" not in type(obj).__name__:
        return (None, None, None)
    msgid = unicode(obj) if isinstance(obj, basestring) else None
    domain = None
    default = None
    try:
        cls = type(obj)
        d = getattr(cls, "domain", None)
        if d is not None and hasattr(d, "__get__"):
            domain = d.__get__(obj, cls)
    except Exception:
        domain = None
    try:
        cls = type(obj)
        d = getattr(cls, "default", None)
        if d is not None and hasattr(d, "__get__"):
            default = d.__get__(obj, cls)
    except Exception:
        default = None
    return (msgid, domain, default)


def _is_arextension_message(obj, domain_filter=None):
    msgid, domain, _ = _msg_accessors(obj)
    if msgid is None:
        return False
    if domain_filter is not None and domain != domain_filter:
        return False
    return domain == AREXTENSION_DOMAIN


def migrate_runtime_titles(portal):
    """Migrate ZODB-stored Folder / FTI titles from write-once localized strings
    back into lazy i18n Message objects so that Title() / FTI.Title() will
    translate at render-time based on the current user language.

    This function is fully idempotent: if the title is already an arextension
    Message with the expected msgid, the object is left untouched.  Existing
    titles that do not match any of the known localized defaults are preserved
    (user customizations will never be overwritten).
    """
    logger.info("*** migrate_runtime_titles (arextension) begin ***")

    folder_ids = list(FOLDER_TITLE_MESSAGES.keys())
    fti_types = list(FTI_TITLE_MESSAGES.keys())
    fti_updated = 0
    fti_skipped = 0
    folder_updated = 0
    folder_skipped = 0

    types_tool = None
    try:
        types_tool = bapi.get_tool("portal_types")
    except Exception:
        types_tool = getattr(portal, "portal_types", None)

    # --- 1) FTI titles -------------------------------------------------------
    if types_tool is not None:
        for portal_type in fti_types:
            fti = getattr(types_tool, portal_type, None)
            if fti is None:
                continue
            expected_msg = _get_fti_expected_title(portal_type)
            expected_mid, _, expected_default_raw = _msg_accessors(expected_msg)
            if expected_msg is None or expected_mid is None:
                continue
            current_raw = getattr(fti, "title", None)
            cur_mid, _, _ = _msg_accessors(current_raw)
            # Unconditionally refresh if previous msgid contained any technical
            # suffix like "Folder/FTI/Listing" or "(Item)" to remove stray
            # literal characters from sidebar / breadcrumbs.
            def _has_technical_suffix(value_uni):
                if not value_uni:
                    return False
                markers = (u"Folder/FTI/Listing", u"(Folder/FTI/Listing)",
                           u"(Item)", u"（Item）", u"folder_title_projects",
                           u"fti_label_", u"Hazard Categories Sample Properties",
                           u"HazardCategories Sample", u"Sample Properties Container",
                           u"Sample Properties (AR Field)")
                return any(m in value_uni for m in markers)

            force_update = False
            if _has_technical_suffix(_to_unicode(current_raw)):
                force_update = True
            if (not force_update and
                _is_arextension_message(current_raw, domain_filter=AREXTENSION_DOMAIN)
                and cur_mid == expected_mid):
                fti_skipped += 1
                continue
            expected_default = _to_unicode(expected_default_raw or u"")
            expected_zh = _to_unicode(translate_with_fallback(
                expected_msg, context=portal,
                languages=("zh_CN", "zh-cn", "zh"), domain=AREXTENSION_DOMAIN))
            current_uni = _to_unicode(current_raw)
            is_arex_msg = _is_arextension_message(
                current_raw, domain_filter=AREXTENSION_DOMAIN)
            allowed = (
                force_update,
                not current_raw,
                current_uni == expected_default,
                expected_default and current_uni == expected_default,
                expected_zh and current_uni == expected_zh,
                (is_arex_msg and cur_mid != expected_mid),
            )
            if not any(allowed):
                fti_skipped += 1
                logger.info("  skip FTI %s custom title=%r", portal_type, current_uni)
                continue
            try:
                try:
                    fti._updateProperty("title", expected_msg)
                except Exception:
                    pass
                try:
                    fti.manage_changeProperties(title=expected_msg)
                except Exception:
                    pass
                fti.title = expected_msg
                for slot in ("_label", "label"):
                    if hasattr(fti, slot):
                        try:
                            setattr(fti, slot, expected_msg)
                        except Exception:
                            pass
                try:
                    fti._p_changed = 1
                except Exception:
                    pass
                fti_updated += 1
                logger.info("  FTI %s title -> Message(msgid=%r)",
                            portal_type, expected_mid)
            except Exception as exc:
                logger.warn("  FTI %s update failed: %s", portal_type, exc)

    # --- 2) Container Folder titles -----------------------------------------
    for folder_id in folder_ids:
        folder = None
        try:
            folder = portal._getOb(folder_id)
        except Exception:
            folder = None
        if folder is None:
            continue
        expected_msg = _get_folder_expected_title(folder_id)
        expected_mid, _, expected_default_raw = _msg_accessors(expected_msg)
        if expected_msg is None or expected_mid is None:
            continue
        current_title = getattr(folder.aq_base, "title", None)
        cur_mid, _, _ = _msg_accessors(current_title)

        def _folder_has_technical_suffix(value_uni):
            if not value_uni:
                return False
            markers = (u"Folder/FTI/Listing", u"(Folder/FTI/Listing)",
                       u"(Item)", u"folder_title_projects", u"fti_label_",
                       u"Hazard Categories Sample Properties",
                       u"HazardCategory Item", u"HazardCategories Sample",
                       u"Sample Properties Container",
                       u"Sample Properties (AR Field)")
            return any(m in value_uni for m in markers)

        force_update = _folder_has_technical_suffix(_to_unicode(current_title))
        if (not force_update and
            _is_arextension_message(current_title, domain_filter=AREXTENSION_DOMAIN)
            and cur_mid == expected_mid):
            folder_skipped += 1
            continue
        expected_default = _to_unicode(expected_default_raw or u"")
        expected_zh = _to_unicode(translate_with_fallback(
            expected_msg, context=portal,
            languages=("zh_CN", "zh-cn", "zh"), domain=AREXTENSION_DOMAIN))
        current_uni = _to_unicode(current_title)
        is_arex_msg = _is_arextension_message(
            current_title, domain_filter=AREXTENSION_DOMAIN)
        allowed = (
            force_update,
            not current_title,
            current_uni == expected_default,
            expected_default and current_uni == expected_default,
            expected_zh and current_uni == expected_zh,
            (is_arex_msg and cur_mid != expected_mid),
        )
        if not any(allowed):
            folder_skipped += 1
            logger.info("  skip folder %s custom title=%r", folder_id, current_uni)
            continue
        try:
            folder.setTitle(expected_msg)
            try:
                folder.reindexObject(idxs=["Title", "sortable_title"])
            except Exception:
                pass
            try:
                folder._p_changed = 1
            except Exception:
                pass
            folder_updated += 1
            logger.info("  folder %s title -> Message(msgid=%r)",
                        folder_id, expected_mid)
        except Exception as exc:
            logger.warn("  folder %s update failed: %s", folder_id, exc)

    logger.info(
        "migrate_runtime_titles done: "
        "FTI updated=%d skipped=%d | Folder updated=%d skipped=%d",
        fti_updated, fti_skipped, folder_updated, folder_skipped)
    return {
        "fti_updated": fti_updated,
        "fti_skipped": fti_skipped,
        "folder_updated": folder_updated,
        "folder_skipped": folder_skipped,
    }


# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------
AR_EXTENSION_FIELD_NAMES = (
    "ProjectNo", "MaterialCode", "MaterialName", "Strength",
    "ManufactureDate", "Quantity", "Unit", "SampleStatus",
    "StorageConditions", "SampleProperties", "SampleRetainer",
    "RetentionTime", "SampleRecovery", "SafetyPrecautions",
)


def uninstall_handler(context):
    marker = "INNOCARE.arextension-uninstall.txt"
    if context.readDataFile(marker) is None:
        return
    uninstall(context)


def uninstall(context):
    """Best-effort cleanup for the AR extension.

    Restores the runtime monkey patch and drops the extension field values
    from existing Analysis Requests. The schema extender registrations
    themselves only go away once the package is removed from the buildout
    and the instance is restarted.
    """
    logger.info("*** INNOCARE.arextension uninstall begin ***")
    portal = None
    try:
        portal = bapi.get_portal()
    except Exception:
        portal = None

    # 1) restore the get_points_of_capture monkey patch (reversible)
    try:
        from bika.lims.browser.analysisrequest.add2 import AnalysisRequestAddView
        from INNOCARE.arextension import patches as _patches
        if (getattr(AnalysisRequestAddView, "get_points_of_capture", None)
                is _patches.patched_get_points_of_capture):
            AnalysisRequestAddView.get_points_of_capture = (
                _patches._original_get_points_of_capture)
            logger.info(
                "arextension uninstall: restored get_points_of_capture")
    except Exception as exc:
        logger.warn("arextension uninstall: patch restore failed: %s", exc)

    # 2) drop extension field values from existing Analysis Requests
    if portal is not None:
        try:
            with ploneapi.env.adopt_roles(["Manager"]):
                pc = bapi.get_tool("portal_catalog")
                brains = list(pc(portal_type="AnalysisRequest"))
                cleaned = 0
                for b in brains:
                    try:
                        obj = b.getObject()
                    except Exception:
                        continue
                    for fname in AR_EXTENSION_FIELD_NAMES:
                        try:
                            if hasattr(obj.aq_base, fname):
                                delattr(obj.aq_base, fname)
                                obj._p_changed = 1
                                cleaned += 1
                        except Exception:
                            continue
                logger.info(
                    "arextension uninstall: cleared %d extension field "
                    "values from %d Analysis Requests",
                    cleaned, len(brains))
        except Exception as exc:
            logger.warn(
                "arextension uninstall: field cleanup failed: %s", exc)

    logger.info("*** INNOCARE.arextension uninstall done ***")
