# -*- coding: utf-8 -*-
"""劫持 take_snapshot（S1）。不含业务逻辑，不改原函数语义。

★ 为什么要打三处而不是一处：`bika.lims.subscribers.auditlog` 和
  `bika.lims.browser.publish.emailview` 都是 `from ... import take_snapshot`，
  各自模块里持有的是**自己的引用**，只改 `api.snapshot` 那一份对它们无效 ——
  漏一处的症状是"部分场景静默不记"，这正是 S1 的头号风险。

★ 为什么只在 store=True 时记：`take_snapshot` 里 `if not store: return snapshot`
  发生在 `storage.append()` **之前**（技术设计 §5.2 实测）。此时
  `get_version(obj)` 拿到的是上一条的版本号，记进去就是错行。
"""

import logging

logger = logging.getLogger("maitux.auditjournal")

_TARGETS = [
    ("bika.lims.api.snapshot", "take_snapshot"),
    ("bika.lims.subscribers.auditlog", "take_snapshot"),
    ("bika.lims.browser.publish.emailview", "take_snapshot"),
]

_patched = False


def _make_wrapper(original):
    def take_snapshot(obj, store=True, **kw):
        snapshot = original(obj, store=store, **kw)
        if store:
            try:
                from . import journal
                journal.buffer(obj, snapshot)
            except Exception:
                # 记录层的任何问题都不允许影响业务保存
                logger.exception("auditjournal: buffer dispatch failed")
        return snapshot

    take_snapshot.__doc__ = getattr(original, "__doc__", None)
    take_snapshot._auditjournal_original = original
    return take_snapshot


def apply_patches():
    """幂等：已打过直接返回。"""
    global _patched
    if _patched:
        return True

    try:
        from bika.lims.api import snapshot as snapshot_api
    except ImportError:
        logger.exception("auditjournal: cannot import bika.lims.api.snapshot, "
                         "recording layer NOT installed")
        return False

    original = getattr(snapshot_api, "take_snapshot", None)
    if original is None:
        logger.error("auditjournal: take_snapshot not found, "
                     "recording layer NOT installed")
        return False
    if getattr(original, "_auditjournal_original", None) is not None:
        _patched = True
        return True

    wrapper = _make_wrapper(original)

    patched, skipped = [], []
    for module_name, attr in _TARGETS:
        try:
            module = __import__(module_name, {}, {}, [attr])
        except ImportError:
            # 某个上游模块改名/消失时不能拖垮启动，但必须显式报出来
            skipped.append("%s (ImportError)" % module_name)
            continue
        current = getattr(module, attr, None)
        if current is None:
            skipped.append("%s (no %s)" % (module_name, attr))
            continue
        if getattr(current, "_auditjournal_original", None) is not None:
            continue
        setattr(module, attr, wrapper)
        patched.append(module_name)

    _patched = bool(patched)
    logger.info("auditjournal: take_snapshot patched in %d/%d module(s): %s",
                len(patched), len(_TARGETS), ", ".join(patched) or "none")
    if skipped:
        # R9：静默降级是本环境的头号敌人，漏打必须留下痕迹
        logger.error("auditjournal: NOT patched: %s "
                     "(those code paths will be missing from the journal)",
                     "; ".join(skipped))
    return _patched
