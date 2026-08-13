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


#: A mass deactivation is by definition many accounts; below this the "missing
#: ratio" carries no signal (one genuine leaver out of two users is 50%).
MIN_MISSING_FOR_GUARD = 5


def _check_missing_is_plausible(stats, missing, tracked, remote_count):
    """Circuit breaker for the "not found in 竹云 -> disable" rule.

    The identifier we store at login (``userinfo.id`` unless 竹云 maps
    ``external_id`` into userinfo) is *assumed* to be the same value that the
    EIAM user list returns as ``user_id``.  If that assumption is ever wrong --
    or if the EIAM API returns a truncated list -- every local account looks
    like a leaver and the naive rule would disable the entire user base in one
    run.  So refuse to deactivate when an implausible share is missing, and say
    so loudly instead.

    Returns whether deactivating the missing accounts may proceed.
    """
    if not config.get("sync_deactivate_missing"):
        return False
    if not missing:
        return True

    if not remote_count:
        # An empty user list is never a legitimate "everybody left"; it means
        # the API answered with nothing useful.  Unconditional stop, no ratio.
        stats["aborted_deactivation"] = True
        stats["errors"].append(
            u"安全保护已触发：竹云用户列表返回 0 条记录，本次不停用任何账号。"
            u"请检查该应用的 EIAM 接口权限（user_read / read）和“限定组织 ID”配置。")
        logger.error("Aborting deactivation: the EIAM user list came back empty")
        return False

    limit = config.get("sync_max_missing_percent")
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 50
    if limit >= 100:                      # explicitly switched off
        return True

    percent = int(round(100.0 * missing / tracked)) if tracked else 100
    if missing < MIN_MISSING_FOR_GUARD or percent <= limit:
        return True

    stats["aborted_deactivation"] = True
    message = (
        u"安全保护已触发：本地 %s 个统一登录账号中有 %s 个（%s%%）在竹云用户列表里"
        u"匹配不到，超过阈值 %s%%，因此本次**不停用任何账号**。"
        u"最常见的原因是登录时存下的唯一 ID 和 EIAM 的 user_id / external_id "
        u"不是同一个字段。请拿 unmatched_sample 里的值去和竹云用户列表核对；"
        u"确认确实是批量离职后，把“允许缺失比例”调高再跑。"
        % (tracked, missing, percent, limit))
    stats["errors"].append(message)
    logger.error(
        "Aborting deactivation: %s/%s (%s%%) local SSO accounts unmatched, "
        "limit is %s%%. Sample of unmatched ids: %s",
        missing, tracked, percent, limit, stats.get("unmatched_sample"))
    return False


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
        "unmatched_sample": [],
        "aborted_deactivation": False,
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
    update_properties = bool(config.get("sync_update_properties"))

    mapping = storage.items(portal)
    stats["local_total"] = len(mapping)

    # -- pass 1: classify everything without writing anything ------------
    plan = []
    for subject, userid in mapping:
        member = users.get_member(portal, userid)
        if member is None:
            plan.append((subject, userid, "forget", None))
            continue
        record = remote.get(u"%s" % subject)
        if record is None:
            plan.append((subject, userid, "missing", None))
        elif _is_truthy(record.get("disabled")):
            plan.append((subject, userid, "disable", u"竹云已停用"))
        elif _is_truthy(record.get("locked")):
            plan.append((subject, userid, "disable", u"竹云已锁定"))
        else:
            plan.append((subject, userid, "keep", record))

    missing = [row for row in plan if row[2] == "missing"]
    tracked = len([row for row in plan if row[2] != "forget"])
    stats["missing"] = len(missing)
    # Opaque identifiers, no personal data -- these are what to compare against
    # the EIAM `user_id` / `external_id` columns when diagnosing a mismatch.
    stats["unmatched_sample"] = [row[0] for row in missing[:5]]

    deactivate_missing = _check_missing_is_plausible(
        stats, len(missing), tracked, remote_count)

    # -- pass 2: apply ---------------------------------------------------
    for subject, userid, action, payload in plan:
        if action == "forget":
            logger.warning("SSO mapping %s -> %s has no member, dropping",
                           subject, userid)
            if not dry_run:
                storage.forget(portal, subject)
        elif action == "missing":
            if deactivate_missing and not dry_run:
                if users.disable_user(
                        portal, userid, u"竹云中已查询不到该用户", timestamp):
                    stats["disabled"] += 1
        elif action == "disable":
            if not dry_run and users.disable_user(
                    portal, userid, payload, timestamp):
                stats["disabled"] += 1
        else:
            if not dry_run and users.enable_user(portal, userid, timestamp):
                stats["enabled"] += 1
            else:
                stats["unchanged"] += 1
            if update_properties and not dry_run:
                if _update_properties(portal, userid, payload):
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
