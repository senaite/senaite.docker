# -*- coding: utf-8 -*-
"""审计流水表的数据库层（S0：DSN 推导 / 连接分桶 / 建表与版本）。

本模块**不认识 SENAITE**，只认识 DSN 和行。两条铁律（技术设计 §2.1）：

  1. 写入路径的函数一律不抛异常，用返回值表达成败 —— 它离业务事务只有一层。
  2. 查询路径可以抛（S7 再实现），查看层报错比静默出空表安全。

★ DSN 里有明文口令：**任何日志、异常信息、兜底文件都只允许出现 mask_dsn() 的结果。**
"""

import hashlib
import logging
import os
import re
import threading

logger = logging.getLogger("maitux.auditjournal")

SCHEMA_VERSION = 1
SCHEMA_COMMENT = "maitux.auditjournal schema v%d"

# 强制集中：运维要跨客户汇总时才设。设了就等于放弃单库备份一致性（实施方案 §6.5）
ENV_DSN = "MAITUX_AUDIT_DSN"
DEFAULT_ZOPE_CONF = "/home/senaite/senaitelims/parts/instance/etc/zope.conf"

# 实施方案 §5 的表结构，逐条 IF NOT EXISTS，可重复执行。
# PostgreSQL 的 DDL 是事务化的：中途失败整批干净回滚。
DDL_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS audit_journal (
        id             bigserial   PRIMARY KEY,
        site_path      text        NOT NULL,
        ts             timestamptz NOT NULL,
        actor          text        NOT NULL,
        action         text,
        portal_type    text        NOT NULL,
        uid            char(32)    NOT NULL,
        obj_id         text,
        obj_title      text,
        obj_path       text,
        review_state   text,
        snapshot_ver   int         NOT NULL,
        remote_address inet,
        roles          text[],
        inserted_at    timestamptz NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS audit_journal_ts_brin "
    "    ON audit_journal USING brin (ts)",
    "CREATE INDEX IF NOT EXISTS audit_journal_site_ts "
    "    ON audit_journal (site_path, ts DESC)",
    "CREATE INDEX IF NOT EXISTS audit_journal_actor_ts "
    "    ON audit_journal (actor, ts DESC)",
    "CREATE INDEX IF NOT EXISTS audit_journal_type_ts "
    "    ON audit_journal (portal_type, ts DESC)",
    "CREATE INDEX IF NOT EXISTS audit_journal_uid_ver "
    "    ON audit_journal (uid, snapshot_ver)",
    # ★ 幂等去重：afterCommitHook 重放、回填、兜底补录都靠它
    "CREATE UNIQUE INDEX IF NOT EXISTS audit_journal_dedup "
    "    ON audit_journal (site_path, uid, snapshot_ver)",
)

_DBNAME_RE = re.compile(r"dbname\s*=\s*'?\"?([^'\"\s]+)")
# zope.conf 里 <postgresql> 段的 dsn 行
_CONF_DSN_RE = re.compile(r"^\s*dsn\s+(.+?)\s*$", re.MULTILINE)

_ensured = set()                 # 已建表的 DSN，进程内去重
_ensured_lock = threading.Lock()
_dsn_by_db = {}             # id(ZODB.DB) -> (db, dsn)；连对象一起存，防 id 复用
_local = threading.local()       # 连接按 DSN 分桶，且每线程独立（技术设计 §7）


# --------------------------------------------------------------------------
# DSN
# --------------------------------------------------------------------------

def mask_dsn(dsn):
    """把 DSN 变成可以安全出现在日志里的短标识：dbname + 指纹，绝不含口令。"""
    if not dsn:
        return "<none>"
    m = _DBNAME_RE.search(dsn)
    dbname = m.group(1) if m else "?"
    digest = hashlib.sha1(dsn.encode("utf-8", "replace")).hexdigest()[:8]
    return "%s#%s" % (dbname, digest)


def _dsn_from_storage(storage):
    """RelStorage 内部属性，跨版本可能变 —— 取不到就静默返回 None，由上层兜底。"""
    try:
        return storage._adapter.connmanager._dsn
    except Exception:
        return None


def dsn_from_zope_conf(path=None):
    """兜底：解析 zope.conf 里根库 <postgresql> 的 dsn 行。"""
    path = path or os.environ.get("ZOPE_CONF") or DEFAULT_ZOPE_CONF
    try:
        with open(path, "rb") as fh:
            text = fh.read().decode("utf-8", "replace")
    except Exception:
        logger.warning("auditjournal: cannot read zope.conf: %r", path)
        return None
    for match in _CONF_DSN_RE.finditer(text):
        candidate = match.group(1).strip()
        if "dbname" in candidate:
            return candidate
    return None


def dsn_for_database(zodb_db):
    """某个 ZODB.DB 对应的 DSN。按 id(db) 缓存 —— 每条快照都会走这里，
    不缓存的话一次工作单提交要重复取几十次（技术设计 §8）。

    ★ 缓存里**连同 DB 对象一起存**（`(db, dsn)`），不是只存 DSN：
      `id()` 在对象被回收后会被复用，只存 DSN 的话，新 DB 对象若拿到同一个
      id，就会读到**上一个库的 DSN** —— 单库下永远不发生，一客户一库下
      就是"某客户的审计行写进另一个客户的库"。存一份强引用即可根除：
      对象不会被回收，id 也就不可能被复用。代价是几个 DB 对象的引用，可忽略。
    """
    if zodb_db is None:
        return None
    key = id(zodb_db)
    cached = _dsn_by_db.get(key)
    if cached is not None:
        cached_db, cached_dsn = cached
        # 双保险：万一真出现 id 复用（理论上被强引用挡掉了），认对象不认 id
        if cached_db is zodb_db:
            return cached_dsn
    dsn = None
    try:
        dsn = _dsn_from_storage(zodb_db.storage)
    except Exception:
        dsn = None
    if dsn:
        _dsn_by_db[key] = (zodb_db, dsn)
    return dsn


def dsn_for(obj=None):
    """该对象应写入哪个库。优先级见 技术设计 §2.1：

    环境变量（强制集中） → 跟随对象所在的库 → zope.conf 的根库。
    三条都失败返回 None，调用方应停用记录并打 error（**不得影响业务**）。
    """
    forced = os.environ.get(ENV_DSN)
    if forced:
        return forced
    if obj is not None:
        try:
            dsn = dsn_for_database(obj._p_jar.db())
            if dsn:
                return dsn
        except Exception:
            pass
    return dsn_from_zope_conf()


# --------------------------------------------------------------------------
# 连接
# --------------------------------------------------------------------------

def _buckets():
    bucket = getattr(_local, "conns", None)
    if bucket is None:
        bucket = {}
        _local.conns = bucket
    return bucket


def get_connection(dsn, force_new=False):
    """按 DSN 分桶的长驻连接，**每线程独立**，不跨线程共享。

    PG 建连 1–3 ms，四个 waitress 线程高频调用会累积，所以不每次新建。
    连接坏掉时 close 掉重连一次由调用方通过 force_new 触发。
    """
    import psycopg2                      # 延迟导入：db 层出问题不该拖垮 import

    bucket = _buckets()
    conn = bucket.get(dsn)
    if conn is not None and not force_new:
        if getattr(conn, "closed", 1) == 0:
            return conn
        bucket.pop(dsn, None)
    if conn is not None and force_new:
        try:
            conn.close()
        except Exception:
            pass
        bucket.pop(dsn, None)
    conn = psycopg2.connect(dsn)
    # ★ Py2 下 psycopg2 默认把 text 列取回成 utf-8 **字节串**。obj_title 里全是中文，
    #   查看层一旦和 unicode 拼接就 UnicodeDecodeError（2026-08-30 干跑实测复现）。
    #   在连接上注册 UNICODE/UNICODEARRAY，读回来的直接是 unicode，与写入侧一致。
    from psycopg2 import extensions as _ext
    _ext.register_type(_ext.UNICODE, conn)
    _ext.register_type(_ext.UNICODEARRAY, conn)
    bucket[dsn] = conn
    return conn


def close_connections():
    """线程退出/测试用。"""
    for dsn, conn in list(_buckets().items()):
        try:
            conn.close()
        except Exception:
            pass
    _local.conns = {}


# --------------------------------------------------------------------------
# 建表与 schema 版本
# --------------------------------------------------------------------------

def _quote(value):
    """COMMENT ON 这类工具语句不能用占位符，只能内联 —— 老老实实转义。"""
    return "'" + value.replace("'", "''") + "'"


# ---- 表结构迁移（实施方案 §8.4）------------------------------------------
#
# 键 = 目标版本，值 = 从「目标版本 - 1」升上来要执行的幂等 DDL。
# 全部必须可重复执行（IF NOT EXISTS / IF EXISTS），因为：
#   * 多库形态下每个库各自补齐，谁先谁后不确定；
#   * 启动时订阅器会跑两遍（§5.6）；
#   * 补录 / 回填也可能触发。
#
# ★ 迁移**不走 GenericSetup upgrade step** —— 那是站点级的，多库形态下
#   在客户 A 的站点上跑只会升到客户 A 的库。这里按 DSN 惰性补齐，两种形态都对。
#   GS 的 upgrade step 只管 profile 侧的元数据变更（见 upgrades/）。
MIGRATIONS = {
    # 2: (
    #     "ALTER TABLE audit_journal ADD COLUMN IF NOT EXISTS foo text",
    # ),
}


def migrate_schema(dsn, from_version):
    """把该库从 from_version 逐级升到 SCHEMA_VERSION。

    :return: True 成功（或无需迁移）/ False 失败（已记日志，不抛）
    """
    if from_version is None or from_version >= SCHEMA_VERSION:
        return True
    conn = None
    try:
        conn = get_connection(dsn)
        cur = conn.cursor()
        for target in range(from_version + 1, SCHEMA_VERSION + 1):
            for stmt in MIGRATIONS.get(target, ()):
                cur.execute(stmt)
            logger.warning("auditjournal: migrated schema v%d -> v%d dsn=%s",
                           target - 1, target, mask_dsn(dsn))
        cur.execute("COMMENT ON TABLE audit_journal IS %s"
                    % _quote(SCHEMA_COMMENT % SCHEMA_VERSION))
        conn.commit()
        return True
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.exception("auditjournal: migration v%s -> v%d failed dsn=%s",
                         from_version, SCHEMA_VERSION, mask_dsn(dsn))
        return False


def read_schema_version(dsn):
    """返回表注释里的 schema 版本号；表不存在或没注释返回 None。"""
    try:
        conn = get_connection(dsn)
        cur = conn.cursor()
        cur.execute("SELECT to_regclass('public.audit_journal')")
        if not cur.fetchone()[0]:
            conn.rollback()
            return None
        cur.execute("SELECT obj_description('audit_journal'::regclass)")
        row = cur.fetchone()
        conn.rollback()
        comment = row[0] if row else None
    except Exception:
        logger.exception("auditjournal: cannot read schema version, dsn=%s",
                         mask_dsn(dsn))
        return None
    if not comment:
        return None
    m = re.search(r"schema v(\d+)", comment)
    return int(m.group(1)) if m else None


def ensure_schema(dsn):
    """对该 DSN 幂等建表 + 建索引 + 比对/升级 schema 版本。

    并发首次调用是安全的：DDL 全是 IF NOT EXISTS，且 PG 的 DDL 事务化。
    :return: True 成功 / False 失败（已记日志，**不抛**）
    """
    if not dsn:
        logger.error("auditjournal: no DSN available, recording disabled")
        return False
    if dsn in _ensured:
        return True

    conn = None
    try:
        conn = get_connection(dsn)
        cur = conn.cursor()
        for stmt in DDL_STATEMENTS:
            cur.execute(stmt)
        cur.execute("SELECT obj_description('audit_journal'::regclass)")
        row = cur.fetchone()
        current = row[0] if row else None
        conn.commit()

        # 惰性版本比对与补齐：注释里的版本比代码旧就逐级迁移（实施方案 §8.4）
        want = SCHEMA_COMMENT % SCHEMA_VERSION
        if current != want:
            found = re.search(r"schema v(\d+)", current or "")
            old_version = int(found.group(1)) if found else 0
            if old_version < SCHEMA_VERSION:
                logger.warning("auditjournal: schema is v%d, code wants v%d "
                               "-> migrating dsn=%s",
                               old_version, SCHEMA_VERSION, mask_dsn(dsn))
                if not migrate_schema(dsn, old_version):
                    return False
            else:
                # 库比代码新：不要动它，降级迁移不存在。记录并停用该库，
                # 免得旧代码往新表里写出错行。
                logger.error("auditjournal: schema v%d is NEWER than code v%d, "
                             "recording disabled for dsn=%s "
                             "(upgrade this package first)",
                             old_version, SCHEMA_VERSION, mask_dsn(dsn))
                return False
    except Exception:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        logger.exception("auditjournal: ensure_schema failed, dsn=%s "
                         "(recording disabled for this database)",
                         mask_dsn(dsn))
        return False

    with _ensured_lock:
        _ensured.add(dsn)
    _log_ready(dsn)
    return True


# 列顺序与 insert_rows 的 row dict 取值顺序必须一致
_COLUMNS = (
    "site_path", "ts", "actor", "action", "portal_type", "uid",
    "obj_id", "obj_title", "obj_path", "review_state", "snapshot_ver",
    "remote_address", "roles",
)

_INSERT_SQL = (
    "INSERT INTO audit_journal (%s) VALUES %%s "
    "ON CONFLICT (site_path, uid, snapshot_ver) DO NOTHING"
) % ", ".join(_COLUMNS)


def insert_rows(dsn, rows):
    """批量 upsert。rows 是 dict 列表，键 = 表列名。

    去重靠唯一索引 (site_path, uid, snapshot_ver) + ON CONFLICT DO NOTHING：
    afterCommitHook 重放、回填、兜底补录都可能送来重复行。

    :return: (ok, inserted_count)；ok=False 时调用方负责走兜底（S3）
    """
    if not rows:
        return True, 0
    try:
        from psycopg2.extras import execute_values
    except ImportError:
        logger.exception("auditjournal: psycopg2.extras unavailable")
        return False, 0

    values = [tuple(row.get(col) for col in _COLUMNS) for row in rows]
    conn = None
    for attempt in (1, 2):          # 连接可能已被 PG 掐断，重连一次再放弃
        try:
            conn = get_connection(dsn, force_new=(attempt == 2))
            cur = conn.cursor()
            execute_values(cur, _INSERT_SQL, values, page_size=200)
            inserted = cur.rowcount
            conn.commit()
            return True, inserted
        except Exception:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            if attempt == 2:
                logger.exception(
                    "auditjournal: insert_rows failed (%d row(s)) dsn=%s",
                    len(rows), mask_dsn(dsn))
                return False, 0
    return False, 0


# ---- 查询（S7 查看层）------------------------------------------------------
#
# ★ 与写入路径相反：**查询路径可以抛异常**。查看层报错让 QA 看见，
#   比静默出一张空表安全得多（技术设计 §2.1 的第二条铁律）。
QUERY_COLUMNS = (
    "id", "ts", "actor", "action", "portal_type", "uid", "obj_id",
    "obj_title", "obj_path", "review_state", "snapshot_ver",
    "remote_address", "roles",
)

def query(dsn, site_path, since, until, actor=None, portal_type=None,
          action=None, keyword=None, cursor=None, backwards=False, limit=25):
    """带筛选的 keyset 分页查询（S8）。

    **keyset 而不是 OFFSET**：按 `(ts, id)` 这个唯一有序对定位游标，
    翻到第几页都只扫 limit 行；OFFSET 在深翻时要跳过前面所有行。
    同时**不跑 `COUNT(*)`** —— 大表上它比查询本身还慢，
    页面也不显示总数（实施方案 §7.2 / 本片判据⑤）。

    :param cursor: (ts, id)，上一页最后一行；None = 第一页
    :param backwards: 往回翻。内部用反序查再翻转，保证顺序一致
    :param limit: 每页行数。实际取 limit+1 行，多出来的那行只用来
                  判断"还有没有下一页"，不返回
    :return: (rows, has_more)
    """
    where = ["site_path = %s", "ts >= %s", "ts < %s"]
    params = [site_path, since, until]

    if actor:
        where.append("actor = %s")
        params.append(actor)
    if portal_type:
        where.append("portal_type = %s")
        params.append(portal_type)
    if action:
        where.append("action = %s")
        params.append(action)
    if keyword:
        # 对象 ID 或标题任一命中即可（实施方案 §7.2）
        where.append("(obj_id ILIKE %s OR obj_title ILIKE %s)")
        like = "%%%s%%" % keyword
        params.extend([like, like])

    if cursor:
        # 行值比较，PostgreSQL 能用上 (site_path, ts DESC) 索引
        where.append("(ts, id) %s (%%s, %%s)" % ("> " if backwards else "< "))
        params.extend([cursor[0], cursor[1]])

    order = "ts ASC, id ASC" if backwards else "ts DESC, id DESC"
    sql = ("SELECT %s FROM audit_journal WHERE %s ORDER BY %s LIMIT %%s"
           % (", ".join(QUERY_COLUMNS), " AND ".join(where), order))
    params.append(limit + 1)

    conn = get_connection(dsn)
    cur = conn.cursor()
    try:
        cur.execute(sql, params)
        records = cur.fetchall()
    finally:
        # 只读查询，结束掉这个事务，别让连接挂在 idle in transaction
        conn.rollback()

    has_more = len(records) > limit
    records = records[:limit]
    rows = [dict(zip(QUERY_COLUMNS, record)) for record in records]
    if backwards:
        rows.reverse()          # 反序查回来的，翻转成与正序一致
    return rows, has_more


def _log_ready(dsn):
    logger.info("auditjournal: table ready, dsn=%s schema v%d",
                mask_dsn(dsn), SCHEMA_VERSION)
    return True
