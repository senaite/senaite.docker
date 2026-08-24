# -*- coding: utf-8 -*-
"""Setup handlers for maitux.roles.

Creates business roles, groups and accounts on first request after restart
and on add-on installation.  All operations are idempotent.
"""
import threading

import plone.api as ploneapi
from Products.CMFPlone.interfaces import INonInstallable
from zope.interface import implementer

from maitux.roles import logger
from maitux.roles.config import DEFAULT_PASSWORD
from maitux.roles.config import ROLE_DEFINITIONS

_INSTALL_LOCK = threading.Lock()
_INSTALL_DONE = False


@implementer(INonInstallable)
class HiddenProfiles(object):

    def getNonInstallableProfiles(self):
        return [
            "maitux.roles:uninstall",
        ]

    def getNonInstallableProducts(self):
        return []


# ---------------------------------------------------------------------------
# Role creation
# ---------------------------------------------------------------------------
def ensure_roles(portal):
    """Add the business roles to the portal if they do not exist yet.

    The GenericSetup rolemap step performs the same task at profile import
    time; this runtime fallback covers the case where the profile has not been
    re-applied on an already existing site.
    """
    valid = set(portal.valid_roles())
    current = list(getattr(portal, "__ac_roles__", ()) or ())
    changed = False
    for rd in ROLE_DEFINITIONS:
        role = rd["role_id"]
        if role not in valid:
            current.append(role)
            changed = True
            logger.info("maitux.roles: adding role %s", role)
    if changed:
        portal.__ac_roles__ = tuple(sorted(set(current)))
    return int(changed)


# ---------------------------------------------------------------------------
# Permission granting
# ---------------------------------------------------------------------------
def _grant_permission(portal, permission, role, acquire=None):
    """Additively grant *role* the *permission* on the portal.

    Existing role grants are preserved; only the new role is appended.
    Returns True if something changed.
    """
    try:
        mappings = portal.rolesOfPermission(permission)
    except Exception:
        # permission unknown (e.g. add-on not installed) -> skip
        return False
    names = [r["name"] for r in mappings
             if r.get("selected") == "SELECTED"]
    if role in names:
        return False
    names.append(role)
    if acquire is None:
        try:
            acquire = portal.acquiredRolesAreUsedBy(permission) == "CHECKED"
        except Exception:
            acquire = True
    try:
        portal.manage_permission(permission, names, acquire=acquire)
        return True
    except Exception as exc:
        logger.warn("maitux.roles: grant %s -> %s failed: %s",
                    role, permission, exc)
        return False


def grant_role_permissions(portal, rd):
    granted = 0
    for permission in rd.get("permissions", []):
        if _grant_permission(portal, permission, rd["role_id"]):
            granted += 1
    return granted


def grant_labmanager_equivalent(portal, rd):
    """Grant every permission LabManager currently has to the given role."""
    role = rd["role_id"]
    granted = 0
    for ps in portal.permission_settings():
        permission = ps["name"]
        try:
            mappings = portal.rolesOfPermission(permission)
        except Exception:
            continue
        has_lab = any(
            r["name"] == "LabManager" and r.get("selected") == "SELECTED"
            for r in mappings)
        if not has_lab:
            continue
        names = [r["name"] for r in mappings
                 if r.get("selected") == "SELECTED"]
        if role in names:
            continue
        names.append(role)
        acquire = ps.get("acquire") == "CHECKED"
        try:
            portal.manage_permission(permission, names, acquire=acquire)
            granted += 1
        except Exception:
            pass
    return granted


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------
def ensure_groups(portal):
    created = 0
    for rd in ROLE_DEFINITIONS:
        group_id = rd["role_id"]
        group = ploneapi.group.get(groupname=group_id)
        if group is None:
            try:
                group = ploneapi.group.create(
                    groupname=group_id,
                    title=rd["title_msg"],
                    description=rd["title_msg"],
                    roles=[group_id],
                )
                created += 1
                logger.info("maitux.roles: created group %s", group_id)
            except Exception as exc:
                logger.warn("maitux.roles: create group %s failed: %s",
                            group_id, exc)
                continue
        else:
            # keep the role assignment in sync (idempotent)
            try:
                ploneapi.group.grant_roles(group=group, roles=[group_id])
            except Exception as exc:
                logger.warn("maitux.roles: grant role %s to group failed: %s",
                            group_id, exc)
    return created


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------
def ensure_users(portal):
    created = 0
    for rd in ROLE_DEFINITIONS:
        username = rd["username"]
        user = ploneapi.user.get(username=username)
        if user is None:
            try:
                user = ploneapi.user.create(
                    email=rd["email"],
                    username=username,
                    password=rd.get("password", DEFAULT_PASSWORD),
                    roles=("Member",),
                    properties={"fullname": rd["title_msg"]},
                )
                created += 1
                logger.info("maitux.roles: created user %s", username)
            except Exception as exc:
                logger.warn("maitux.roles: create user %s failed: %s",
                            username, exc)
                continue
        # ensure membership in the matching group (idempotent)
        group_id = rd["role_id"]
        group = ploneapi.group.get(groupname=group_id)
        if group is None:
            continue
        try:
            groups = [g.getId() for g in
                      ploneapi.group.get_groups(user=user)]
        except Exception:
            groups = []
        if group_id not in groups:
            try:
                ploneapi.group.add_user(group=group, user=user)
            except Exception as exc:
                logger.warn("maitux.roles: add user %s to group %s failed: %s",
                            username, group_id, exc)
    return created


def migrate_role_titles(portal):
    """Re-point stored group titles and user fullnames to the maitux.roles
    domain (replaces legacy arextension-domain Messages created before the
    domain split). Idempotent.
    """
    updated = 0
    group_tool = None
    try:
        group_tool = ploneapi.portal.get_tool("portal_groups")
    except Exception:
        group_tool = None
    for rd in ROLE_DEFINITIONS:
        group_id = rd["role_id"]
        if group_tool is not None and group_tool.getGroupById(group_id):
            try:
                group_tool.editGroup(
                    group_id,
                    title=rd["title_msg"],
                    description=rd["title_msg"],
                )
                updated += 1
            except Exception as exc:
                logger.warn("roles: group %s title update failed: %s",
                            group_id, exc)
        user = ploneapi.user.get(username=rd["username"])
        if user is not None:
            try:
                user.setMemberProperties({"fullname": rd["title_msg"]})
                updated += 1
            except Exception as exc:
                logger.warn("roles: user %s fullname update failed: %s",
                            rd["username"], exc)
    return updated


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
def run_install_steps(portal):
    logger.info("*** maitux.roles run_install_steps begin ***")
    with ploneapi.env.adopt_roles(["Manager"]):
        ensure_roles(portal)
        granted = 0
        for rd in ROLE_DEFINITIONS:
            granted += grant_role_permissions(portal, rd)
            if rd.get("inherit_labmanager"):
                granted += grant_labmanager_equivalent(portal, rd)
        logger.info("maitux.roles: granted %d permissions", granted)
        created_groups = ensure_groups(portal)
        created_users = ensure_users(portal)
        migrate_role_titles(portal)
    logger.info(
        "*** maitux.roles run_install_steps done "
        "(groups=%d users=%d) ***",
        created_groups, created_users)


def _get_portal(context=None):
    """Resolve the Plone site with the same fallbacks used by other addons."""
    if context is not None:
        try:
            site = context.getSite()
            if site is not None:
                return site
        except Exception:
            pass
    try:
        from bika.lims import api as bapi
        portal = bapi.get_portal()
        if portal is not None:
            return portal
    except Exception:
        pass
    try:
        portal = ploneapi.portal.get()
        if portal is not None:
            return portal
    except Exception:
        pass
    return None


def post_install(context):
    logger.info("maitux.roles post install [BEGIN]")
    portal = _get_portal(context)
    if portal is None:
        logger.warn("maitux.roles: portal not found, post install skipped")
        return
    run_install_steps(portal)
    logger.info("maitux.roles post install [DONE]")


def on_process_starting(event):
    try:
        from zope.component import provideHandler
        from ZPublisher.interfaces import IPubAfterTraversal
        provideHandler(_on_first_request, (IPubAfterTraversal,))
        logger.info("maitux.roles: registered first-request hook "
                    "(IPubAfterTraversal)")
    except Exception as exc:
        logger.warn("maitux.roles: hook registration failed: %s", exc)


def _on_first_request(event):
    global _INSTALL_DONE
    if _INSTALL_DONE:
        return
    with _INSTALL_LOCK:
        if _INSTALL_DONE:
            return
        try:
            request = getattr(event, "request", None)
            if request is None:
                return
            # make sure plone.api can resolve the request context
            try:
                from zope.globalrequest import getRequest, setRequest
                if getRequest() is None:
                    setRequest(request)
            except Exception:
                pass
            portal = _get_portal()
            if portal is None:
                logger.warn("maitux.roles: first-request hook: "
                            "portal not resolvable, retry next request")
                return
            run_install_steps(portal)
            import transaction
            transaction.commit()
            _INSTALL_DONE = True
            logger.info("maitux.roles: first-request hook committed")
        except Exception as exc:
            logger.warn("maitux.roles: first-request hook failed: %s", exc)
            import traceback
            logger.warn(traceback.format_exc())


# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------
def _strip_role_from_permissions(portal, role):
    """Remove *role* from every permission rolemap on the portal."""
    stripped = 0
    try:
        settings = portal.permission_settings()
    except Exception:
        return 0
    for ps in settings:
        permission = ps["name"]
        try:
            mappings = portal.rolesOfPermission(permission)
        except Exception:
            continue
        names = [r["name"] for r in mappings
                 if r.get("selected") == "SELECTED"]
        if role not in names:
            continue
        names.remove(role)
        acquire = ps.get("acquire") == "CHECKED"
        try:
            portal.manage_permission(permission, names, acquire=acquire)
            stripped += 1
        except Exception:
            continue
    return stripped


def uninstall_handler(context):
    marker = "%s-uninstall.txt" % "maitux.roles"
    if context.readDataFile(marker) is None:
        return
    uninstall(context)


def uninstall(context):
    """Remove the business roles, groups and accounts created at install.

    Idempotent: objects that are already gone are simply skipped.
    """
    logger.info("maitux.roles uninstall [BEGIN]")
    portal = _get_portal(context)
    if portal is None:
        logger.warn("maitux.roles uninstall: portal not found, skip")
        return
    role_ids = [rd["role_id"] for rd in ROLE_DEFINITIONS]
    usernames = [rd["username"] for rd in ROLE_DEFINITIONS]

    removed_users = 0
    removed_groups = 0
    removed_roles = 0

    with ploneapi.env.adopt_roles(["Manager"]):
        # 1) accounts
        for username in usernames:
            user = ploneapi.user.get(username=username)
            if user is None:
                continue
            try:
                ploneapi.user.delete(username=username)
                removed_users += 1
                logger.info("maitux.roles uninstall: deleted user %s", username)
            except Exception as exc:
                logger.warn("maitux.roles uninstall: delete user %s failed: %s",
                            username, exc)
        # 2) groups
        for group_id in role_ids:
            group = ploneapi.group.get(groupname=group_id)
            if group is None:
                continue
            try:
                ploneapi.group.delete(groupname=group_id)
                removed_groups += 1
                logger.info("maitux.roles uninstall: deleted group %s", group_id)
            except Exception as exc:
                logger.warn("maitux.roles uninstall: delete group %s failed: %s",
                            group_id, exc)
        # 3) roles (from __ac_roles__ and every permission rolemap)
        current_roles = set(getattr(portal, "__ac_roles__", ()) or ())
        for role in role_ids:
            if role not in current_roles:
                continue
            try:
                remaining = [r for r in current_roles if r != role]
                portal.__ac_roles__ = tuple(remaining)
                current_roles = set(remaining)
                stripped = _strip_role_from_permissions(portal, role)
                removed_roles += 1
                logger.info("maitux.roles uninstall: deleted role %s "
                            "(stripped %d permissions)", role, stripped)
            except Exception as exc:
                logger.warn("maitux.roles uninstall: delete role %s failed: %s",
                            role, exc)

    logger.info(
        "maitux.roles uninstall [DONE] (users=%d groups=%d roles=%d)",
        removed_users, removed_groups, removed_roles)
