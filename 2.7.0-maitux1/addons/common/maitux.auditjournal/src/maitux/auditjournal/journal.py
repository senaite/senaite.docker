# -*- coding: utf-8 -*-
"""缓冲 + afterCommitHook 批量写入（S1：最简版，兜底文件在 S3）。

本模块不认识 HTTP，也不拼 SQL。三条纪律：

  1. `buffer()` 全程 try/except —— 它挂在业务保存路径上，异常绝不能冒出去。
  2. 事务回滚（status=False）时整批丢弃：ZODB 没落盘，PG 也不该有行。
  3. 无论走哪条路，`_flush` 结束时缓冲区必须为空，否则会串到下一个请求。

★ 缓冲区逐条带 DSN，flush 时按 DSN 分组：一个请求理论上可以跨库
  （多库形态，技术设计 §5.5），不能假设一个请求只有一个库。
"""

import json
import logging
import os
import re
import threading

import transaction

from . import db

logger = logging.getLogger("maitux.auditjournal")

# waitress 默认 4 线程，缓冲区必须是 thread-local（技术设计 §7）
_local = threading.local()

# dsn_for 三条全失败时整体停用，避免每条快照都刷一次 error
_disabled = False

# inet 列只接受合法地址；X-Forwarded-For 可能是 "a, b" 或垃圾值，非法一律转 None
_IPV4 = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
_IPV6 = re.compile(r"^[0-9A-Fa-f:]{2,45}$")


def _u(value):
    """任何值 -> unicode 或 None。psycopg2 对 unicode 是安全的（技术设计 §6）。"""
    if value is None:
        return None
    if isinstance(value, unicode):  # noqa: F821 (Py2)
        return value
    if isinstance(value, str):
        return value.decode("utf-8", "replace")
    return unicode(value)  # noqa: F821 (Py2)


def _clean_ip(value):
    if not value:
        return None
    text = _u(value).strip()
    # X-Forwarded-For 可能是逗号分隔链，取第一跳
    if "," in text:
        text = text.split(",")[0].strip()
    if _IPV4.match(text) or (":" in text and _IPV6.match(text)):
        return text
    return None


# 兜底文件：PG 写不进去时行落这里，恢复后由 S6 补录（实施方案 §6.3）
FALLBACK_PATH = os.environ.get(
    "MAITUX_AUDIT_FALLBACK", "/data/log/audit_journal_fallback.jsonl")
_fallback_lock = threading.Lock()


def _fallback_write(dsn, rows):
    """把写不进 PG 的行落到兜底文件，每行一条 JSON。

    ★ 只写 `mask_dsn()` 的结果，**不写完整 DSN** —— DSN 带明文口令，
      落到文件里就多一处泄露面（CLAUDE.md §8.7）。补录时按掩码反查真实 DSN
      （实施方案 §6.3 的第二个选项 / SPEC 未决问题 1 的倾向）。
      文件权限仍按 0600 建，双保险。

    写失败只 logger.error，**绝不往上抛** —— 它在业务保存之后，抛了也没人能处理。
    """
    try:
        directory = os.path.dirname(FALLBACK_PATH)
        if directory and not os.path.isdir(directory):
            os.makedirs(directory, 0o700)
        payload = []
        for row in rows:
            record = dict(row)
            record["dsn"] = db.mask_dsn(dsn)
            # ensure_ascii=False：中文按原样写，方便人直接看（技术设计 §6.4）
            payload.append(json.dumps(record, ensure_ascii=False))
        blob = (u"\n".join(payload) + u"\n").encode("utf-8")

        with _fallback_lock:
            fd = os.open(FALLBACK_PATH,
                         os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                os.write(fd, blob)
            finally:
                os.close(fd)
        logger.error("auditjournal: %d row(s) written to fallback file "
                     "(dsn=%s), pending replay", len(rows), db.mask_dsn(dsn))
        return True
    except Exception:
        # 兜底的兜底：文件也写不了（磁盘满/权限），只能留日志，
        # 之后靠 ZODB 全量回填补（实施方案 §6.3）
        logger.exception("auditjournal: fallback write failed, %d row(s) lost "
                         "(dsn=%s)", len(rows), db.mask_dsn(dsn))
        return False


def _site_path(obj):
    """该对象**自己所属**站点的完整路径。

    ★ 不要用 `api.get_portal()`：它是 `ploneapi.portal.getSite()`，
      取的是**当前请求上下文**的站点，且**不接受参数**
      （技术设计 §4 写成 `api.get_portal(obj)` 是错的，2026-08-30 实测
      `TypeError: get_portal() takes no arguments`）。
      一客户一库形态下，挂载库里的对象必须按对象自己往上走才拿得对。
    """
    from Acquisition import aq_parent
    from Products.CMFPlone.interfaces import IPloneSiteRoot

    node = obj
    while node is not None:
        if IPloneSiteRoot.providedBy(node):
            return "/".join(node.getPhysicalPath())
        parent = aq_parent(node)
        if parent is node:
            break
        node = parent

    # 兜底：当前请求的站点（单库形态下与上面等价）
    from bika.lims import api
    return "/".join(api.get_portal().getPhysicalPath())


def _rows():
    rows = getattr(_local, "rows", None)
    if rows is None:
        rows = []
        _local.rows = rows
    return rows


def _build_row(obj, snapshot):
    """快照元数据 -> 表列（技术设计 §4）。取字段全程防御：

    take_snapshot 自己不查 supports_snapshots（§5.1），所以调用方可能是
    api.create() / emailview 这类没做过检查的路径，对象不一定"可审计"。
    """
    from bika.lims import api
    from bika.lims.api import snapshot as snapshot_api

    meta = snapshot.get("__metadata__") or {}

    return {
        # 站点完整路径，不是 site id —— 一客户一库下 id 全叫 lims（实施方案 §5）
        "site_path": _u(_site_path(obj)),
        "ts": meta.get("snapshot_created"),
        "actor": _u(meta.get("actor")) or u"(unknown)",
        "action": _u(meta.get("action")) or None,
        "portal_type": _u(api.get_portal_type(obj)),
        "uid": api.get_uid(obj),
        "obj_id": _u(api.get_id(obj)),
        # ★ 中文重灾区，必须过 unicode 边界
        "obj_title": _u(api.get_title(obj)),
        "obj_path": _u(api.get_path(obj)),
        "review_state": _u(meta.get("review_state")) or None,
        # ★ 必须在 storage.append() 之后取，拿到的才是本条的版本号（§5.2）
        "snapshot_ver": snapshot_api.get_version(obj),
        "remote_address": _clean_ip(meta.get("remote_address")),
        "roles": [_u(r) for r in (meta.get("roles") or [])],
    }


def buffer(obj, snapshot):
    """把一条快照的元数据推入本线程缓冲区，首次推入时注册 afterCommitHook。"""
    global _disabled
    if _disabled:
        return
    try:
        dsn = db.dsn_for(obj)
        if not dsn:
            _disabled = True
            logger.error("auditjournal: no DSN for %r, recording disabled "
                         "for this process", obj)
            return

        row = _build_row(obj, snapshot)
        row["_dsn"] = dsn

        # ★ 按事务对象跟踪，不能用"缓冲区是否为空"判断该不该挂钩子。
        #   实测（2026-08-30）：transaction 的 afterCommitHook 在 **abort 时根本
        #   不会被调用**，也不会带到下一个事务。若按"空/非空"判断：请求一出错
        #   → abort → _flush 从未运行 → 残行留在 thread-local → 下次 first 恒为
        #   False → **再也不注册钩子**，该 waitress 线程从此永久停止记录。
        txn = transaction.get()
        if getattr(_local, "txn", None) is not txn:
            stale = getattr(_local, "rows", None)
            if stale:
                # 上一个事务被 abort 了：那批行本来就不该入库，丢弃是正确语义
                logger.info("auditjournal: dropped %d row(s) from an aborted "
                            "transaction", len(stale))
            _local.rows = []
            _local.txn = txn
            txn.addAfterCommitHook(_flush)
        _rows().append(row)
    except Exception:
        # 该条丢失，但本次保存必须照常成功
        logger.exception("auditjournal: buffer failed for %r", obj)


def _flush(status):
    """afterCommitHook 回调。status=False 表示事务回滚，整批丢弃。"""
    rows = _rows()
    _local.rows = []          # ★ 无论后面发生什么，缓冲区先清空
    _local.txn = None         # 下一条快照会开新事务、重新挂钩子
    if not rows:
        return
    if not status:
        logger.info("auditjournal: transaction aborted, dropped %d row(s)",
                    len(rows))
        return

    groups = {}
    for row in rows:
        groups.setdefault(row.pop("_dsn"), []).append(row)

    for dsn, group in groups.items():
        try:
            if not db.ensure_schema(dsn):
                # 建表都失败（库连不上/权限没了）→ 行不能丢，落兜底文件
                _fallback_write(dsn, group)
                continue
            ok, count = db.insert_rows(dsn, group)
            if ok:
                logger.debug("auditjournal: inserted %d row(s) dsn=%s",
                             count, db.mask_dsn(dsn))
            else:
                _fallback_write(dsn, group)
        except Exception:
            # 走到这里说明是意料之外的异常；仍然先保住行，再留痕
            logger.exception("auditjournal: flush failed dsn=%s",
                             db.mask_dsn(dsn))
            _fallback_write(dsn, group)
