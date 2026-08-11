import logging
import os
from StringIO import StringIO

from OFS.Image import manage_addImage
from Products.CMFCore.utils import getToolByName
from plone.registry.interfaces import IRegistry
from zope.component import getUtility


logger = logging.getLogger("maitux.branding")

LOGO_ID = "maitu-logo-png"
LOGO_TITLE = "maitu-logo-png"
LOGO_FILENAME = "logo.png"
LOGO_CONTENT_TYPE = "image/png"
LOGO_URL = u"/%s" % LOGO_ID
LOGO_STYLES = {"height": "40px"}
PORTAL_TITLE = "MaituLiMS"

REGISTRY_VALUES = (
    ("plone.toolbar_logo", LOGO_URL),
    ("senaite.toolbar_logo", LOGO_URL),
    ("senaite.toolbar_logo_styles", LOGO_STYLES),
)


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


def _get_logo_path():
    return os.path.join(os.path.dirname(__file__), "resources", LOGO_FILENAME)


def _read_logo_data():
    logo_path = _get_logo_path()
    with open(logo_path, "rb") as handle:
        return handle.read()


def _install_logo(site):
    logo_data = _read_logo_data()
    if site._getOb(LOGO_ID, None) is not None:
        site.manage_delObjects([LOGO_ID])

    manage_addImage(
        site,
        LOGO_ID,
        StringIO(logo_data),
        title=LOGO_TITLE,
        content_type=LOGO_CONTENT_TYPE,
    )


def _apply_registry_settings():
    registry = getUtility(IRegistry)
    for record_name, value in REGISTRY_VALUES:
        record = registry.records.get(record_name)
        if record is None:
            logger.warning("Registry record '%s' not found", record_name)
            continue
        record.value = value


def post_install(portal_setup):
    logger.info("MAITUX.BRANDING install handler [BEGIN]")
    site = _get_site(portal_setup)
    site.setTitle(PORTAL_TITLE)
    _install_logo(site)
    _apply_registry_settings()
    logger.info("MAITUX.BRANDING install handler [DONE]")

