# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from bika.lims import api as bapi

from INNOCARE.arextension import logger


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
        ensure_sample_catalog_projectno_index(portal)
    except Exception as exc:
        logger.warn("ensure_sample_catalog_projectno_index failed: %s", exc)
    logger.info("*** INNOCARE.arextension post_install_setup done ***")


# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------
UNINSTALL_MARKER = "INNOCARE.arextension-uninstall.txt"


def uninstall(context):
    """安全的卸载：只拆结构/行为，绝不动业务数据。

    做三件事：
      1. 还原全部 monkey patch（patches.restore_all，仅行为还原）；
      2. 移除本 addon 自己的 ``ProjectNo`` index（结构，非数据）；
      3. 移除 browserlayer ``IARExtensionLayer``。

    明确不做（硬约束）：
      - 不 ``delattr`` AR 扩展字段值（保留业务数据，卸载后成为孤儿属性，
        重新装回 addon 后原样恢复）；
      - 不删 ``usage_scope`` index（解耦后归 maitux.hazardcategories）；
      - 不删 HazardCategory 数据（归 maitux.hazardcategories）。
    """
    if context.readDataFile(UNINSTALL_MARKER) is None:
        return

    logger.info("*** INNOCARE.arextension uninstall begin ***")

    portal = None
    try:
        portal = bapi.get_portal()
    except Exception:
        portal = None

    # 1) 还原全部 monkey patch（只还原行为，不删数据）
    try:
        from INNOCARE.arextension import patches as _patches
        _patches.restore_all()
    except Exception as exc:
        logger.warn("arextension uninstall: patch restore failed: %s", exc)

    # 2) 移除自己的 ProjectNo index（结构，非数据）
    if portal is not None:
        sc = None
        try:
            sc = bapi.get_tool("senaite_catalog_sample")
        except Exception:
            sc = getattr(portal, "senaite_catalog_sample", None)
        if sc is not None:
            try:
                if "ProjectNo" in sc.indexes():
                    from senaite.core.api.catalog import del_index as _del_index
                    _del_index(sc, "ProjectNo")
                    logger.info(
                        "arextension uninstall: removed ProjectNo index")
            except Exception as exc:
                logger.warn(
                    "arextension uninstall: delIndex ProjectNo failed: %s",
                    exc)

    # 3) 移除 browserlayer
    try:
        from plone.browserlayer import utils as layer_utils
        layer_utils.unregister_layer(name="INNOCARE.arextension")
        logger.info("arextension uninstall: unregistered browser layer")
    except Exception as exc:
        logger.warn(
            "arextension uninstall: browserlayer unregister failed: %s", exc)

    logger.info("*** INNOCARE.arextension uninstall done ***")
