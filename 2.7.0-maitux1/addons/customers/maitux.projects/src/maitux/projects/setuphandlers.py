# -*- coding: utf-8 -*-

from bika.lims import api as bika_api
from plone import api as ploneapi
from Products.CMFPlone.interfaces import INonInstallable
from zope.interface import implementer

from maitux.projects import _
from INNOCARE.arextension.setuphandlers import translate_with_fallback
from maitux.projects.config import PROJECTNAME
from maitux.projects.config import PROFILE_ID
from maitux.projects.config import PROJECTS_FOLDER_ID
from maitux.projects.config import PROJECTS_FOLDER_TITLE_MSG
from maitux.projects.config import PROJECTS_FOLDER_TITLE
from maitux.projects.config import SIDEBAR_DEPTH

import logging
logger = logging.getLogger("maitux.projects")

FOLDER_ID = PROJECTS_FOLDER_ID
FOLDER_TITLE_MSG = PROJECTS_FOLDER_TITLE_MSG
FOLDER_TITLE = PROJECTS_FOLDER_TITLE
FOLDER_TYPE = "Projects"
ITEM_TYPE = "Project"
DEFAULT_LAYOUT = "view"

FTI_CONTAINER_LABEL_MSG = _(u"fti_label_projects_container", default=u"Projects container")
FTI_ITEM_LABEL_MSG = _(u"fti_label_project_item", default=u"Project item")
PROJECT_TITLE_MSG = _(u"fti_title_project", default=u"Project")

PROFILE_ID_STEP = PROFILE_ID


@implementer(INonInstallable)
class HiddenProfiles(object):

    def getNonInstallableProfiles(self):
        return [
            "%s:uninstall" % PROJECTNAME,
        ]

    def getNonInstallableProducts(self):
        return []


def _translate_msg(portal, msg):
    return translate_with_fallback(msg, context=portal)


def _portal_from_context_or_global(context=None):
    portal = None
    try:
        portal = bika_api.get_portal()
    except Exception:
        portal = None
    if portal is None and context is not None:
        try:
            from zope.app.component.hooks import getSite
            portal = getSite()
        except Exception:
            pass
    if portal is None and context is not None:
        try:
            portal = getattr(context, "aq_parent", None)
        except Exception:
            pass
    return portal


def _get_tool(portal, name):
    try:
        return portal[name]
    except Exception:
        try:
            from Products.CMFCore.utils import getToolByName
            return getToolByName(portal, name)
        except Exception:
            return None


def _get_senaite_setup(portal):
    # 必须 dict-style 访问 portal['bika_setup']，因为 bin/instance run 下
    # Acquisition 会让 portal.get(...) 返回 RequestContainer！
    try:
        if 'bika_setup' in portal:
            s = portal['bika_setup']
            if s is not None and hasattr(s, 'getSidebarFolders'):
                return s
    except Exception:
        pass
    try:
        if 'setup' in portal:
            s = portal['setup']
            if s is not None and hasattr(s, 'getSidebarFolders'):
                return s
    except Exception:
        pass
    try:
        return bika_api.get_senaite_setup()
    except Exception:
        return None


def setup_handler(context):
    marker = "%s.txt" % PROJECTNAME
    if context.readDataFile(marker) is None:
        return
    logger.info("maitux.projects setup handler [BEGIN]")
    portal = _portal_from_context_or_global(context) or (
        getattr(context, "getSite", lambda: None)())
    if portal is None:
        logger.warn("portal not available in setup_handler, skip")
        return
    run_install_steps(portal)
    logger.info("maitux.projects setup handler [DONE]")


def post_install(context):
    logger.info("maitux.projects post install [BEGIN]")
    portal = (getattr(context, "getSite", lambda: None)()
              or _portal_from_context_or_global(context))
    if portal is None:
        logger.warn("portal not available in post_install, skip")
        return
    run_install_steps(portal)
    logger.info("maitux.projects post install [DONE]")


def run_install_steps(portal):
    setup_type_constraints(portal)
    folder = setup_site_structure(portal)
    migrate_projects_titles(portal)
    setup_permissions(portal, folder)
    setup_sidebar(portal)
    reindex_structure(folder)
    ensure_projects_workflow_initialized(portal)


def migrate_projects_titles(portal):
    """Set Projects folder + FTI titles to maitux.projects-domain Messages.

    Replaces the legacy titles (plain strings or other-domain Messages) so
    runtime translation resolves through the maitux.projects catalog.
    Idempotent: setting the same Message again is harmless.
    """
    types_tool = _get_tool(portal, "portal_types")
    updated = 0
    mapping = {
        FOLDER_TYPE: FOLDER_TITLE_MSG,
        ITEM_TYPE: PROJECT_TITLE_MSG,
    }
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
            logger.info("projects: FTI %s title -> Message (maitux.projects)",
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
            logger.info("projects: folder %s title -> Message (maitux.projects)",
                        FOLDER_ID)
        except Exception as exc:
            logger.warn("projects: folder title update failed: %s", exc)
    return updated


def setup_type_constraints(portal):
    logger.info("*** Setup Projects Type Constraints ***")
    types_tool = _get_tool(portal, "portal_types")
    if types_tool is None:
        raise RuntimeError("portal_types tool not found")

    # 1) 先跑 GenericSetup typeinfo / workflow（单数名，非 workflows）
    setup_tool = _get_tool(portal, "portal_setup")
    if setup_tool is not None:
        try:
            setup_tool.runImportStepFromProfile(
                PROFILE_ID_STEP, "typeinfo")
            logger.info("Ran 'typeinfo' import step from %s", PROFILE_ID_STEP)
        except Exception as exc:
            logger.warn("typeinfo import failed: %s", exc)
        try:
            setup_tool.runImportStepFromProfile(
                PROFILE_ID_STEP, "workflow")
            logger.info("Ran 'workflow' import step from %s",
                        PROFILE_ID_STEP)
        except Exception as exc:
            logger.warn("workflow import failed: %s", exc)
    else:
        logger.warn("portal_setup not found, skip GenericSetup import")

    # 2) 如果 GenericSetup 没成功建 FTI，就手动用 DexterityFTI 建（兜底终极保险）
    ensure_fti_manually(portal, types_tool, FOLDER_TYPE, FTI_CONTAINER_LABEL_MSG)
    ensure_fti_manually(portal, types_tool, ITEM_TYPE, FTI_ITEM_LABEL_MSG)

    # 3) allowed_content_types 追加
    ensure_allowed_content_type(types_tool, "Plone Site", FOLDER_TYPE)

    folder_fti = types_tool.getTypeInfo(FOLDER_TYPE)
    if folder_fti is None:
        raise RuntimeError(
            "FTI '%s' still missing after GenericSetup + manual ensure"
            % FOLDER_TYPE)
    allowed = list(getattr(folder_fti, "allowed_content_types", ()) or ())
    if ITEM_TYPE not in allowed:
        allowed.append(ITEM_TYPE)
        folder_fti.manage_changeProperties(
            allowed_content_types=tuple(allowed))
        logger.info("Added '%s' to allowed_content_types of '%s'",
                    ITEM_TYPE, FOLDER_TYPE)

    # 4) 绑定 Project -> senaite_batch_workflow（与核心 Batch 保持一致；强制覆盖）
    wf_tool = _get_tool(portal, "portal_workflow")
    if wf_tool is not None:
        try:
            target_chain = ("senaite_batch_workflow",)
            current = wf_tool.getChainForPortalType(ITEM_TYPE)
            if tuple(current) != target_chain:
                wf_tool.setChainForPortalTypes((ITEM_TYPE,), target_chain)
                logger.info(
                    "Set workflow chain for '%s' -> %s (was %s)",
                    ITEM_TYPE, target_chain, current)
            else:
                logger.info(
                    "Skip workflow chain '%s': already %s",
                    ITEM_TYPE, target_chain)
        except Exception as exc:
            logger.warn(
                "set workflow chain for '%s' failed: %s", ITEM_TYPE, exc)
        try:
            target_folder_chain = ("senaite_one_state_workflow",)
            current_folder = wf_tool.getChainForPortalType(FOLDER_TYPE)
            if tuple(current_folder) != target_folder_chain:
                wf_tool.setChainForPortalTypes(
                    (FOLDER_TYPE,), target_folder_chain)
                logger.info(
                    "Set workflow chain for '%s' -> %s (was %s)",
                    FOLDER_TYPE, target_folder_chain, current_folder)
        except Exception as exc:
            logger.warn(
                "set workflow chain for '%s' failed: %s",
                FOLDER_TYPE, exc)


def ensure_fti_manually(portal, types_tool, portal_type, label_msg):
    if portal_type == FOLDER_TYPE:
        title_msg = _(u"fti_label_projects_container", default=u"Projects")
    else:
        title_msg = _(u"fti_label_project_item", default=u"Project")
    if portal_type == FOLDER_TYPE:
        final_label_msg = _(u"fti_label_projects_container", default=u"Projects")
    else:
        final_label_msg = _(u"fti_label_project_item", default=u"Project")
    existing = types_tool.getTypeInfo(portal_type)
    folder_is = (portal_type == FOLDER_TYPE)
    klass = ("maitux.projects.content.projects.Projects"
             if folder_is else
             "maitux.projects.content.project.Project")
    schema = ("maitux.projects.content.projects.IProjectsSchema"
              if folder_is else
              "maitux.projects.content.project.IProjectSchema")
    immediate_view = DEFAULT_LAYOUT if folder_is else "view"
    default_view = DEFAULT_LAYOUT if folder_is else "view"
    factory = FOLDER_TYPE if folder_is else ITEM_TYPE
    add_perm = "cmf.AddPortalContent"
    global_allow = folder_is  # Folder: allow global (portal 根可建)
    allowed_types = ()
    if folder_is:
        allowed_types = (ITEM_TYPE,)
    behaviors = (
        "plone.app.dexterity.behaviors.metadata.IBasic",
        "plone.app.referenceablebehavior.referenceable.IReferenceable",
    )
    view_methods = (
        (DEFAULT_LAYOUT, "projects_listing", "view")
        if folder_is else ("view",))
    aliases = {
        "(Default)": "(dynamic view)",
        "edit": "@@edit",
        "sharing": "@@sharing",
        "view": "(selected layout)",
    }
    icon_expr = ("string:${portal_url}/++plone++senaite.core.static/assets/icons/"
                 + ("batch.svg" if folder_is else "batchfolder.svg"))
    add_view_expr = "string:${folder_url}/++add++%s" % factory

    if existing is not None:
        logger.info(
            "FTI '%s' already exists, force-sync ALL attrs (klass/schema/"
            "view_methods/aliases/default_view/behaviors...)", portal_type)
        fti = existing
        changed = False
        for (attr, expected) in (
            ('title', title_msg),
            ('description', final_label_msg),
            ('icon_expr', icon_expr),
            ('factory', factory),
            ('add_view_expr', add_view_expr),
            ('immediate_view', immediate_view),
            ('global_allow', bool(global_allow)),
            ('filter_content_types', True),
            ('allowed_content_types', tuple(allowed_types)),
            ('allow_discussion', False),
            ('default_view', default_view),
            ('view_methods', tuple(view_methods)),
            ('default_view_fallback', False),
            ('add_permission', add_perm),
            ('schema', schema),
            ('klass', klass),
            ('behaviors', tuple(behaviors)),
        ):
            actual = getattr(fti, attr, None)
            if attr in ('allowed_content_types', 'view_methods', 'behaviors'):
                if tuple(actual or ()) != tuple(expected):
                    try:
                        setattr(fti, attr, tuple(expected))
                        changed = True
                        logger.info("  sync %s: %s -> %s",
                                    attr, actual, expected)
                    except Exception as exc:
                        logger.warn("  sync %s failed: %s", attr, exc)
            else:
                if actual != expected:
                    try:
                        setattr(fti, attr, expected)
                        changed = True
                        logger.info("  sync %s: %r -> %r",
                                    attr, actual, expected)
                    except Exception as exc:
                        logger.warn("  sync %s failed: %s", attr, exc)
        try:
            actual_aliases = dict(fti.getMethodAliases() or {})
        except Exception:
            actual_aliases = {}
        if actual_aliases != aliases:
            try:
                fti._setAliases(aliases)
                changed = True
                logger.info("  sync aliases: %s -> %s", actual_aliases, aliases)
            except Exception as exc:
                logger.warn("  sync aliases failed: %s", exc)
        if changed:
            try:
                fti.manage_changeProperties(
                    title=title_msg,
                    description=final_label_msg,
                    immediate_view=immediate_view,
                    default_view=default_view,
                    global_allow=bool(global_allow),
                    filter_content_types=True,
                    allowed_content_types=tuple(allowed_types),
                    allow_discussion=False,
                    default_view_fallback=False,
                    add_permission=add_permission,
                )
            except Exception:
                pass
        logger.info(
            "FTI '%s' sync done (changed=%s)", portal_type, changed)
        return

    try:
        from plone.dexterity.fti import DexterityFTI
    except ImportError:
        try:
            from Products.CMFDynamicViewFTI.fti import (
                DynamicViewTypeInformation as DexterityFTI)
        except ImportError:
            raise RuntimeError(
                "Cannot import DexterityFTI for manual FTI creation")

    fti = DexterityFTI(portal_type)
    fti.title = title_msg
    fti.description = final_label_msg
    fti.icon_expr = icon_expr
    fti.factory = factory
    fti.add_view_expr = add_view_expr
    fti.immediate_view = immediate_view
    fti.global_allow = bool(global_allow)
    fti.filter_content_types = True
    fti.allowed_content_types = tuple(allowed_types)
    fti.allow_discussion = False
    fti.default_view = default_view
    fti.view_methods = tuple(view_methods)
    fti.default_view_fallback = False
    fti.add_permission = add_perm
    fti.schema = schema
    fti.klass = klass
    fti.behaviors = tuple(behaviors)
    try:
        fti._setAliases(aliases)
    except Exception:
        pass
    try:
        types_tool._setObject(portal_type, fti)
    except Exception as exc:
        logger.warn(
            "_setObject raised for FTI '%s' (%s); direct attr set fallback",
            portal_type, exc)
        try:
            from Acquisition import Implicit
            if not hasattr(types_tool, '_objects'):
                types_tool._objects = ()
            existing_meta = dict(
                [(o['id'], o) for o in types_tool._objects])
            if portal_type not in existing_meta:
                new_meta = list(types_tool._objects) + [
                    {'id': portal_type, 'meta_type': fti.meta_type}]
                types_tool._objects = tuple(new_meta)
            types_tool._setOb(portal_type, fti)
            try:
                fti.id = portal_type
            except Exception:
                pass
        except Exception as inner_exc:
            logger.error(
                "Direct _setOb fallback also failed for '%s': %s",
                portal_type, inner_exc)
            raise RuntimeError(
                "Failed to register Dexterity FTI %s by any mean"
                % portal_type)
    logger.info(
        "Manually registered Dexterity FTI '%s' (klass=%s, schema=%s)",
        portal_type, klass, schema)


def ensure_allowed_content_type(types_tool, type_name, allowed_type):
    fti = types_tool.getTypeInfo(type_name)
    if fti is None:
        logger.warn(
            "FTI '%s' not found, skip allowed_content_types append for '%s'",
            type_name, allowed_type)
        return
    try:
        filter_flag = getattr(fti, "filter_content_types", None)
        if not filter_flag:
            try:
                fti.manage_changeProperties(filter_content_types=True)
                logger.info("Set filter_content_types=True for '%s'",
                            type_name)
            except Exception:
                pass
    except Exception:
        pass
    allowed = list(getattr(fti, "allowed_content_types", ()) or ())
    if allowed_type in allowed:
        logger.info("Skip allowed_content_types update for '%s' -> '%s'",
                    type_name, allowed_type)
        return
    allowed.append(allowed_type)
    try:
        fti.manage_changeProperties(allowed_content_types=tuple(allowed))
        logger.info("Added '%s' to allowed_content_types of '%s'",
                    allowed_type, type_name)
    except Exception as exc:
        logger.warn(
            "manage_changeProperties failed for %s -> %s: %s",
            type_name, allowed_type, exc)


def setup_site_structure(portal):
    logger.info("*** Setup Projects Site Structure ***")
    msgid = u"folder_title_projects"
    default = u"Projects"
    FOLDER_TITLE_MSG = _(msgid, default=default)
    with ploneapi.env.adopt_roles(["Manager"]):
        existing = None
        try:
            existing = portal[FOLDER_ID]
        except Exception:
            existing = None
        if existing is not None:
            existing_type = getattr(existing, "portal_type", "")
            if existing_type == FOLDER_TYPE:
                logger.info(
                    "Skip existing folder '%s' (%s)",
                    FOLDER_ID, FOLDER_TYPE)
                folder = existing
            else:
                logger.info(
                    "Existing '%s' is type '%s', replacing with '%s'",
                    FOLDER_ID, existing_type, FOLDER_TYPE)
                folder = _replace_with_projects_fti(portal, existing, FOLDER_TITLE_MSG)
        else:
            try:
                folder = ploneapi.content.create(
                    container=portal,
                    type=FOLDER_TYPE,
                    id=FOLDER_ID,
                    title=FOLDER_TITLE_MSG,
                )
                logger.info(
                    "Created folder '%s' with type '%s'",
                    FOLDER_ID, FOLDER_TYPE)
            except Exception as exc1:
                logger.warn(
                    "ploneapi.content.create for '%s' failed (%s); "
                    "fallback to Dexterity _constructInstance",
                    FOLDER_ID, exc1)
                folder_fti = portal.portal_types.getTypeInfo(FOLDER_TYPE)
                if folder_fti is None:
                    raise RuntimeError(
                        "FTI '%s' still unavailable for raw create"
                        % FOLDER_TYPE)
                with ploneapi.env.adopt_roles(["Manager"]):
                    new_id = folder_fti._constructInstance(
                        portal, FOLDER_ID, title=FOLDER_TITLE_MSG)
                    if not new_id and FOLDER_ID in portal:
                        new_id = FOLDER_ID
                    if not new_id:
                        raise RuntimeError(
                            "_constructInstance returned empty id for '%s'"
                            % FOLDER_TYPE)
                    folder = portal[new_id]
                    logger.info(
                        "Fallback created folder '%s' with type '%s'",
                        FOLDER_ID, FOLDER_TYPE)

        try:
            current_layout = folder.getLayout()
            if current_layout != DEFAULT_LAYOUT:
                folder.setLayout(DEFAULT_LAYOUT)
                logger.info(
                    "Set layout of '%s' to '%s' (was %s)",
                    FOLDER_ID, DEFAULT_LAYOUT, repr(current_layout))
            else:
                logger.info("Layout of '%s' is already '%s'",
                            FOLDER_ID, DEFAULT_LAYOUT)
        except Exception as exc:
            logger.warn("setLayout for '%s' failed: %s", FOLDER_ID, exc)
        return folder


def _replace_with_projects_fti(portal, existing, translated_title=None):
    if translated_title is None:
        translated_title = _translate_msg(portal, FOLDER_TITLE_MSG)
    folder_title = (getattr(existing, "Title", lambda: translated_title)()
                    or translated_title)
    legacy_id = "{}_legacy".format(FOLDER_ID)
    idx = 1
    while legacy_id in portal:
        legacy_id = "{}_legacy_{}".format(FOLDER_ID, idx)
        idx += 1

    renamed_ok = False
    try:
        portal.manage_renameObject(FOLDER_ID, legacy_id)
        renamed_ok = True
        logger.info("Renamed legacy folder to '%s'", legacy_id)
    except Exception as exc:
        logger.warn("Rename failed, using del fallback: %s", exc)
    if not renamed_ok:
        try:
            portal.manage_delObjects([FOLDER_ID])
            logger.info("Deleted legacy folder '%s'", FOLDER_ID)
        except Exception as exc2:
            logger.warn("Delete failed: %s", exc2)

    folder = ploneapi.content.create(
        container=portal,
        type=FOLDER_TYPE,
        id=FOLDER_ID,
        title=folder_title if folder_title else translated_title,
    )
    logger.info("Created new '%s' with type '%s'", FOLDER_ID, FOLDER_TYPE)
    return folder


def setup_permissions(portal, folder):
    logger.info("*** Setup Projects Permissions ***")
    if folder is None:
        return
    roles = ["LabClerk", "LabManager", "Manager", "Owner"]
    targets = [folder]
    for cid in list(getattr(folder, "objectIds", lambda: [])()):
        targets.append(folder[cid])

    for obj in targets:
        try:
            obj.manage_permission("View", roles=roles, acquire=1)
            obj.manage_permission(
                "Access contents information", roles=roles, acquire=1)
            obj.reindexObjectSecurity()
        except Exception:
            continue
    logger.info("Updated permissions for %s object(s) under %s",
                len(targets), bika_api.get_path(folder))


def setup_sidebar(portal):
    logger.info("*** Setup Projects Sidebar ***")
    setup_tool = _get_senaite_setup(portal)
    if setup_tool is None:
        raise RuntimeError("SENAITE setup tool not found")

    get_folders = getattr(setup_tool, "getSidebarFolders", None)
    set_folders = getattr(setup_tool, "setSidebarFolders", None)
    if callable(get_folders) and callable(set_folders):
        folders = list(get_folders())
        if FOLDER_ID not in folders:
            folders.append(FOLDER_ID)
            set_folders(tuple(folders))
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
            logger.info(
                "Skip sidebar depth update, current depth is %s", current)


def reindex_structure(folder):
    logger.info("*** Reindex Projects Structure ***")
    if folder is None:
        return
    targets = [folder]
    for cid in list(getattr(folder, "objectIds", lambda: [])()):
        targets.append(folder[cid])
    for obj in targets:
        try:
            obj.reindexObject()
        except Exception:
            continue
    logger.info("Reindexed %s object(s) under %s",
                len(targets), bika_api.get_path(folder))


def uninstall(context):
    logger.info("maitux.projects uninstall [BEGIN]")

    portal = (getattr(context, "getSite", lambda: None)()
              or _portal_from_context_or_global(context))
    if portal is None:
        logger.warn("portal not available in uninstall, skip")
        return

    setup_tool = _get_senaite_setup(portal)
    if setup_tool is not None:
        get_folders = getattr(setup_tool, "getSidebarFolders", None)
        set_folders = getattr(setup_tool, "setSidebarFolders", None)
        if callable(get_folders) and callable(set_folders):
            folders = list(get_folders())
            if FOLDER_ID in folders:
                folders.remove(FOLDER_ID)
                set_folders(tuple(folders))
                logger.info(
                    "Removed '%s' from SENAITE sidebar folders", FOLDER_ID)

    logger.info("maitux.projects uninstall [DONE]")


# ==============================================================================
# Workflow initialization (ensure senaite_batch_workflow always has state)
# ==============================================================================

def on_project_added(event):
    """Subscriber: after Project is added, initialize its workflow state.

    Dexterity + portal_workflow sometimes fails to set the initial review
    state for newly-bound workflow chains; this handler guarantees the
    object ends up in the ``open`` state of ``senaite_batch_workflow``.
    """
    try:
        obj = event.object
    except Exception:
        return
    try:
        from Acquisition import aq_inner
        inner = aq_inner(obj)
        if getattr(inner, "portal_type", None) != ITEM_TYPE:
            return
        from Products.CMFCore.interfaces import ISiteRoot
        from zope.component import getUtility, ComponentLookupError
        try:
            portal = getUtility(ISiteRoot)
        except ComponentLookupError:
            try:
                portal = inner.getPhysicalRoot()["lims"]
            except Exception:
                portal = None
        if portal is None:
            return
        wf_tool = _get_tool(portal, "portal_workflow")
        if wf_tool is None:
            return
        _ensure_single_workflow_initialized(wf_tool, inner)
    except Exception:
        # Never raise inside an event subscriber
        pass


def _ensure_single_workflow_initialized(wf_tool, obj):
    """Idempotent: set status of senaite_batch_workflow for one Project obj.

    Returns True if any modification was made, False otherwise.
    """
    from Acquisition import aq_inner
    inner = aq_inner(obj)
    if getattr(inner, "portal_type", None) != ITEM_TYPE:
        return False
    modified = False
    # 1) Make sure the object-level chain points to senaite_batch_workflow
    try:
        current_chain = tuple(wf_tool.getChainFor(inner) or ())
    except Exception:
        current_chain = ()
    target = ("senaite_batch_workflow",)
    if tuple(current_chain) != target:
        try:
            wf_tool.setChainForPortalTypes((ITEM_TYPE,), target)
            modified = True
        except Exception:
            pass
    # 2) If review_state still MISSING -> initialize senaite_batch_workflow
    try:
        rs = wf_tool.getInfoFor(inner, "review_state", "MISSING")
    except Exception:
        rs = "MISSING"
    if rs in ("MISSING", None, ""):
        try:
            initial = "open"
            wf_tool.setStatusOf("senaite_batch_workflow", inner, initial)
            modified = True
        except Exception:
            # senaite_batch_workflow id on this object may differ; try all
            try:
                for wf_id in tuple(wf_tool.getChainFor(inner) or ()):
                    try:
                        wf_tool.setStatusOf(wf_id, inner, "open")
                        modified = True
                    except Exception:
                        continue
            except Exception:
                pass
    # 3) Always reindex after changes so catalog review_state column is fresh
    if modified:
        try:
            inner.reindexObject()
        except Exception:
            pass
    return modified


def ensure_projects_workflow_initialized(portal):
    """Walk every Project in ``portal['projects']`` and repair workflow state.

    Idempotent; safe to call from the Add-ons Install button repeatedly.
    """
    from Acquisition import aq_inner
    wf_tool = _get_tool(portal, "portal_workflow")
    if wf_tool is None:
        logger.warn("ensure_projects_workflow_initialized: no wf_tool")
        return
    folder = (aq_inner(portal.get(FOLDER_ID)) if hasattr(portal, 'get')
              else None)
    if folder is None or FOLDER_ID not in portal:
        return
    try:
        folder = aq_inner(portal[FOLDER_ID])
    except Exception:
        return

    total = 0
    fixed = 0
    try:
        items = list(folder.objectItems())
    except Exception:
        items = []
    for oid, obj in items:
        try:
            if getattr(aq_inner(obj), "portal_type", None) != ITEM_TYPE:
                continue
            total += 1
            if _ensure_single_workflow_initialized(wf_tool, obj):
                fixed += 1
        except Exception:
            continue
    if total:
        logger.info(
            "ensure_projects_workflow_initialized: scanned=%d fixed=%d",
            total, fixed)



