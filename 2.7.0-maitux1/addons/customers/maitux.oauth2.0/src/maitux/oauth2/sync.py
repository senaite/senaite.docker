# -*- coding: utf-8 -*-
"""Daily user synchronisation against the 竹云 EIAM user directory.

竹云 offers no leaver notification, so once a day we pull the whole user list
(``GET /api/v2/tenant/users``) and disable every locally known SSO account that
is reported as ``disabled``/``locked`` -- or that has disappeared from the
directory altogether.
"""

import json
from datetime import datetime

from maitux.oauth2 import config
from maitux.oauth2 import logger
from maitux.oauth2 import safe_text
from maitux.oauth2 import storage
from maitux.oauth2 import users
from maitux.oauth2.client import BCastleClient


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _is_truthy(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return u"%s" % value in (u"1", u"true", u"True", u"yes", u"Y")


def _index_remote_users(client):
    """``{id_value: record}`` for every configured id field of every user."""
    fields = [f.strip() for f in
              (config.get("sync_user_id_field") or u"").replace("\n", ",").split(",")
              if f.strip()]
    if not fields:
        fields = ["external_id", "user_id"]

    index = {}
    count = 0
    for record in client.iter_eiam_users():
        count += 1
        for field in fields:
            value = record.get(field)
            if value in (None, ""):
                continue
            index[u"%s" % value] = record
    return index, count


def sync_users(portal, dry_run=False):
    """Run one synchronisation pass.  Returns a stats dict."""
    stats = {
        "started": _now(),
        "finished": None,
        "remote_total": 0,
        "local_total": 0,
        "disabled": 0,
        "enabled": 0,
        "updated": 0,
        "unchanged": 0,
        "missing": 0,
        "errors": [],
        "dry_run": bool(dry_run),
    }

    if not config.is_enabled():
        stats["errors"].append(u"统一登录总开关未启用")
        stats["finished"] = _now()
        return stats
    if not config.get("sync_enabled"):
        stats["errors"].append(u"用户同步未启用")
        stats["finished"] = _now()
        return stats

    try:
        remote, remote_count = _index_remote_users(BCastleClient())
    except Exception as exc:
        logger.error("EIAM user sync failed: %s", safe_text(exc))
        stats["errors"].append(u"拉取竹云用户列表失败：%s" % safe_text(exc))
        stats["finished"] = _now()
        _record(stats)
        return stats

    stats["remote_total"] = remote_count
    timestamp = _now()
    deactivate_missing = bool(config.get("sync_deactivate_missing"))
    update_properties = bool(config.get("sync_update_properties"))

    mapping = storage.items(portal)
    stats["local_total"] = len(mapping)

    for subject, userid in mapping:
        member = users.get_member(portal, userid)
        if member is None:
            logger.warning("SSO mapping %s -> %s has no member, dropping",
                           subject, userid)
            if not dry_run:
                storage.forget(portal, subject)
            continue

        record = remote.get(u"%s" % subject)
        if record is None:
            stats["missing"] += 1
            if deactivate_missing:
                if not dry_run and users.disable_user(
                        portal, userid, u"竹云中已查询不到该用户", timestamp):
                    stats["disabled"] += 1
            continue

        if _is_truthy(record.get("disabled")) or _is_truthy(record.get("locked")):
            reason = u"竹云已停用" if _is_truthy(record.get("disabled")) else u"竹云已锁定"
            if not dry_run and users.disable_user(portal, userid, reason, timestamp):
                stats["disabled"] += 1
            continue

        if not dry_run and users.enable_user(portal, userid, timestamp):
            stats["enabled"] += 1
        else:
            stats["unchanged"] += 1

        if update_properties and not dry_run:
            if _update_properties(portal, userid, record):
                stats["updated"] += 1

    stats["finished"] = _now()
    if not dry_run:
        _record(stats)
    logger.info(
        "IdP user sync finished: remote=%(remote_total)s local=%(local_total)s "
        "disabled=%(disabled)s reenabled=%(enabled)s missing=%(missing)s",
        stats)
    return stats


def _update_properties(portal, userid, record):
    member = users.get_member(portal, userid)
    if member is None:
        return False
    properties = {}
    fullname = record.get("name") or record.get("user_name")
    email = record.get("email")
    if fullname and users.member_property(member, "fullname", u"") != fullname:
        properties["fullname"] = fullname
    if email and users.member_property(member, "email", u"") != email:
        properties["email"] = email
    if not properties:
        return False
    return users.set_member_properties(portal, userid, properties)


def _record(stats):
    summary = dict(stats)
    summary["errors"] = [u"%s" % e for e in stats.get("errors") or []]
    config.set_value("last_sync", u"%s" % (stats.get("finished") or _now()))
    try:
        dumped = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True)
        if isinstance(dumped, bytes):
            dumped = dumped.decode("utf-8", "replace")
        config.set_value("last_sync_result", dumped)
    except Exception as exc:  # pragma: no cover
        logger.warning("Could not store sync summary: %s", safe_text(exc))
