# -*- coding: utf-8 -*-
"""启动时把表准备好。

为什么用 IDatabaseOpenedWithRoot 而不是 import 时做：
  * import 发生在 ZCML 加载期，那时数据库层还没打开；
  * 这个事件拿得到已打开的 DB 对象，DSN 直接从 RelStorage 取，
    不必解析 zope.conf（多库形态下 zope.conf 也只有根库）。

★ 本函数**绝不允许抛异常**：它跑在启动链路上，抛出去就是整站起不来。
  但也不能静默 —— 失败要留下 logger.exception，否则就成了 R9 说的静默失效。
"""

import logging
import os

from . import db

logger = logging.getLogger("maitux.auditjournal")


def _iter_databases(zodb_db):
    """根库 + 所有挂载库（一客户一库形态下客户库在这里）。"""
    seen = []
    try:
        databases = getattr(zodb_db, "databases", None) or {}
        for candidate in databases.values():
            if candidate not in seen:
                seen.append(candidate)
    except Exception:
        pass
    if zodb_db not in seen:
        seen.append(zodb_db)
    return seen


def on_database_opened(event):
    """IDatabaseOpenedWithRoot 处理器：逐库幂等建表。"""
    try:
        forced = os.environ.get(db.ENV_DSN)
        if forced:
            # 强制集中：所有库的记录都进这一个 DSN，只需准备它
            dsns = [forced]
        else:
            dsns = []
            for zodb_db in _iter_databases(getattr(event, "database", None)):
                dsn = db.dsn_for_database(zodb_db)
                # TemporaryStorage 之类没有 DSN，跳过是正常的
                if dsn and dsn not in dsns:
                    dsns.append(dsn)
            if not dsns:
                fallback = db.dsn_from_zope_conf()
                if fallback:
                    dsns.append(fallback)

        if not dsns:
            logger.error("auditjournal: no DSN derived at startup, "
                         "recording disabled")
            return

        for dsn in dsns:
            db.ensure_schema(dsn)

        # ★ 与技术设计 §1 的图有一处刻意偏差：图里 patches 由 __init__ 在 import
        #   时调用。改在这里，是因为本包由 autoinclude 在 CMFPlone 的 ZCML 里加载，
        #   那一刻 bika.lims 的各子模块不保证都已 import 完；在 import 期强行拉起
        #   它们容易踩循环导入。DatabaseOpenedWithRoot 时全部产品已加载，且还没有
        #   任何请求进来 —— 不会漏记，风险更低。
        from . import patches
        patches.apply_patches()
    except Exception:
        # 兜到最外层：宁可不记审计，也不能让实例起不来
        logger.exception("auditjournal: startup ensure_schema crashed, "
                         "recording may be unavailable")
