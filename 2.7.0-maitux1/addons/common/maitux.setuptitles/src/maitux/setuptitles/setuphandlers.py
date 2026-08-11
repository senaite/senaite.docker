from Products.CMFCore.utils import getToolByName
from zope.annotation.interfaces import IAnnotations

from maitux.setuptitles import logger


ANNOTATION_KEY = "maitux.setuptitles.original_titles"

TITLE_MAP = {
    "analysiscategories": u"\u5206\u6790\u7c7b\u522b",
    "instrumenttypes": u"\u4eea\u5668\u7c7b\u578b",
    "sampletypes": u"\u6837\u54c1\u7c7b\u578b",
}

DEFAULT_TITLES = {
    "analysiscategories": "Analysis Categories",
    "instrumenttypes": "Instrument Types",
    "sampletypes": "Sample Types",
}


def _get_site(portal_setup):
    get_site = getattr(portal_setup, "getSite", None)
    if callable(get_site):
        return get_site()

    portal_url = getToolByName(portal_setup, "portal_url", None)
    if portal_url is not None:
        return portal_url.getPortalObject()

    current = getattr(portal_setup, "aq_parent", None)
    while current is not None:
        get_site = getattr(current, "getSite", None)
        if callable(get_site):
            return get_site()
        if getattr(current, "portal_type", None) == "Plone Site":
            return current
        current = getattr(current, "aq_parent", None)

    raise AttributeError("Unable to resolve Plone site from setup context")


def _get_setup_container(site):
    return site._getOb("setup", None)


def _get_object(setup_container, object_id):
    if setup_container is None:
        return None
    return setup_container._getOb(object_id, None)


def _get_title(obj):
    if obj is None:
        return None
    title = None
    if hasattr(obj, "Title"):
        title = obj.Title()
    if not title:
        title = getattr(obj, "title", None)
    return title


def _set_title(obj, title):
    if obj is None:
        return
    if hasattr(obj, "setTitle"):
        obj.setTitle(title)
    if hasattr(obj, "manage_changeProperties"):
        obj.manage_changeProperties(title=title)
    elif not hasattr(obj, "setTitle"):
        setattr(obj, "title", title)
    if hasattr(obj, "reindexObject"):
        obj.reindexObject(idxs=["Title"])


def _store_original_titles(site):
    annotations = IAnnotations(site)
    stored = annotations.get(ANNOTATION_KEY, {})
    setup_container = _get_setup_container(site)

    for object_id in TITLE_MAP:
        if object_id not in stored:
            obj = _get_object(setup_container, object_id)
            stored[object_id] = _get_title(obj)

    annotations[ANNOTATION_KEY] = stored
    return stored


def _apply_titles(site, mapping):
    setup_container = _get_setup_container(site)
    if setup_container is None:
        logger.warning("SENAITE setup container not found")
        return

    for object_id, title in mapping.items():
        obj = _get_object(setup_container, object_id)
        if obj is None:
            logger.warning("Setup object '%s' not found", object_id)
            continue
        _set_title(obj, title)
        logger.info("Updated '%s' title to '%s'", object_id, title)


def pre_install(portal_setup):
    logger.info("MAITUX.SETUPTITLES pre-install handler [BEGIN]")
    logger.info("MAITUX.SETUPTITLES pre-install handler [DONE]")


def post_install(portal_setup):
    logger.info("MAITUX.SETUPTITLES install handler [BEGIN]")
    site = _get_site(portal_setup)
    _store_original_titles(site)
    _apply_titles(site, TITLE_MAP)
    logger.info("MAITUX.SETUPTITLES install handler [DONE]")


def pre_uninstall(portal_setup):
    logger.info("MAITUX.SETUPTITLES pre-uninstall handler [BEGIN]")
    logger.info("MAITUX.SETUPTITLES pre-uninstall handler [DONE]")


def post_uninstall(portal_setup):
    logger.info("MAITUX.SETUPTITLES uninstall handler [BEGIN]")
    site = _get_site(portal_setup)
    annotations = IAnnotations(site)
    stored = annotations.get(ANNOTATION_KEY, {})
    restore_map = {}

    for object_id, default_title in DEFAULT_TITLES.items():
        restore_map[object_id] = stored.get(object_id) or default_title

    _apply_titles(site, restore_map)

    if ANNOTATION_KEY in annotations:
        del annotations[ANNOTATION_KEY]

    logger.info("MAITUX.SETUPTITLES uninstall handler [DONE]")
