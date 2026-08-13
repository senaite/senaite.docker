# -*- coding: utf-8 -*-
"""GenericSetup handlers."""

from Products.CMFCore.utils import getToolByName
from Products.CMFPlone.interfaces import INonInstallable
from plone import api
from zope.interface import implementer

from maitux.oauth2 import config
from maitux.oauth2 import logger
from maitux.oauth2 import safe_text
from maitux.oauth2 import state
from maitux.oauth2.users import MEMBERDATA_PROPERTIES


#: The control panel entry is registered from code rather than from a
#: GenericSetup ``controlpanel.xml``.  On Plone 5.2 / Python 2 the XML importer
#: (Products.CMFPlone.exportimport.controlpanel._initConfiglets) does
#: ``str(child.getAttribute('title'))``, which raises UnicodeEncodeError for a
#: non-ASCII title and aborts the whole installation.  registerConfiglet()
#: passes `name` straight through to PloneConfiglet, so calling it directly
#: keeps the Chinese title without needing a translation catalogue.
CONFIGLET_ID = "maitux-oauth2"
CONFIGLET_TITLE = u"竹云统一登录 (OAuth 2.0)"
CONFIGLET_DESCRIPTION = u"对接竹云 IDaaS 的 OAuth 2.0 统一登录配置。"


@implementer(INonInstallable)
class HiddenProfiles(object):

    def getNonInstallableProfiles(self):
        return ["maitux.oauth2:uninstall"]


def _unregister_configlet(portal):
    tool = getToolByName(portal, "portal_controlpanel", None)
    if tool is None:  # pragma: no cover
        return
    try:
        tool.unregisterConfiglet(CONFIGLET_ID)
    except Exception:
        # Not registered yet -- nothing to do.
        pass


def _register_configlet(portal):
    tool = getToolByName(portal, "portal_controlpanel", None)
    if tool is None:  # pragma: no cover
        logger.warning("portal_controlpanel is missing, no control panel entry")
        return
    _unregister_configlet(portal)          # keep re-installs idempotent
    try:
        with api.env.adopt_roles(["Manager"]):
            tool.registerConfiglet(
                id=CONFIGLET_ID,
                name=CONFIGLET_TITLE,
                action="string:${portal_url}/@@oauth2-controlpanel",
                permission="Manage portal",
                category="Products",
                appId="maitux.oauth2",
                visible=1,
                icon_expr="",
                description=CONFIGLET_DESCRIPTION,
            )
        logger.info("Registered control panel entry %s", CONFIGLET_ID)
    except Exception as exc:
        logger.warning("Could not register control panel entry: %s",
                       safe_text(exc))


def _add_memberdata_properties(portal):
    tool = getToolByName(portal, "portal_memberdata", None)
    if tool is None:  # pragma: no cover
        logger.warning("portal_memberdata is missing, cannot add properties")
        return
    for name, kind, default in MEMBERDATA_PROPERTIES:
        if tool.hasProperty(name):
            continue
        try:
            tool.manage_addProperty(name, default, kind)
            logger.info("Added memberdata property %s (%s)", name, kind)
        except Exception as exc:
            logger.warning("Could not add memberdata property %s: %s",
                           name, safe_text(exc))


def _create_pending_group(portal):
    groupname = (config.get("pending_group") or u"").strip()
    if not groupname:
        return
    if api.group.get(groupname=groupname) is not None:
        return
    try:
        api.group.create(
            groupname=groupname,
            title=u"待授权（统一登录）",
            description=u"通过竹云统一登录首次创建、尚未获得 LIMS 权限的账号。"
                        u"给用户分配任意 LIMS 角色，或把用户移出本组，即视为已授权。",
            roles=[],
        )
        logger.info("Created pending group %s", groupname)
    except Exception as exc:
        logger.warning("Could not create group %s: %s", groupname, safe_text(exc))


def post_install(context):
    portal = api.portal.get()
    _add_memberdata_properties(portal)
    _create_pending_group(portal)
    _register_configlet(portal)
    state.ensure_secret()
    logger.info(
        "maitux.oauth2 installed. Callback URL: %s/@@oauth2-callback",
        portal.absolute_url())


def uninstall(context):
    """Drop the control panel entry but leave the member data alone.

    Member properties and the subject mapping are deliberately kept so that a
    re-install does not orphan every SSO account.
    """
    _unregister_configlet(api.portal.get())
    logger.info("maitux.oauth2 uninstalled (member data has been preserved)")
