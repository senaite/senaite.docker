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


@implementer(INonInstallable)
class HiddenProfiles(object):

    def getNonInstallableProfiles(self):
        return ["maitux.oauth2:uninstall"]


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
    state.ensure_secret()
    logger.info(
        "maitux.oauth2 installed. Callback URL: %s/@@oauth2-callback",
        portal.absolute_url())


def uninstall(context):
    """Leave the member data alone -- only drop the control panel entry.

    Member properties and the subject mapping are deliberately kept so that a
    re-install does not orphan every SSO account.
    """
    logger.info("maitux.oauth2 uninstalled (member data has been preserved)")
