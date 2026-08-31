# -*- coding: utf-8 -*-
"""审计流水检索视图（S7 列表 + S8 筛选与分页）。

四条硬约束，来自实施方案 §7、技术设计 §5.3 与本片判据：

1. **权限必须在入口卡死**。本视图直接读 SQL，**绕过了对象级权限过滤** ——
   实测同一 catalog 上 `searchResults()` 返回 66、`unrestrictedSearchResults()`
   返回 0，差异全部来自权限。走 SQL 就等于没有那一层。
2. **对象已被移除的行默认不显示**（决策 D）。表 append-only 一条不删；
   一致性放在查询层。**不提供"显示已移除对象"开关。**
3. **判定孤儿必须批量**：`uid_catalog(UID=[...])` 一次查询，且只能用该行
   所属站点的 catalog。
4. **时间窗必须有默认值、有跨度上限**（本片 6 个月），**超限拒绝而不是静默截断** ——
   审计界面上"看起来对但其实少了"比报错危险得多。
"""

import logging
from datetime import datetime, timedelta

from Products.Five.browser import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from zope.i18nmessageid import MessageFactory

from .. import db

logger = logging.getLogger("maitux.auditjournal")

# ★ 用户可见文案一律走 MessageFactory，msgid 保持 ASCII（R9b）；
#   中文只出现在 locales/zh_CN 的 .po 里。
_ = MessageFactory("maitux.auditjournal")

# 默认时间窗（实施方案 §7.2）
DEFAULT_DAYS = 7

# ★ 单次查询的跨度上限。超过就拒绝，要求用户分段查（2026-08-31 产品决定）。
#   改这个值要同步改 Runbook 里的说明。
MAX_RANGE_DAYS = 183           # 约 6 个月

PAGE_SIZE = 25
DATE_FMT = "%Y-%m-%d"


class AuditJournalView(BrowserView):
    """`<site>/@@audit-journal`"""

    template = ViewPageTemplateFile("templates/journal.pt")

    def __init__(self, context, request):
        super(AuditJournalView, self).__init__(context, request)
        self.error = None
        self._rows = None
        self._has_more = False

    def __call__(self):
        return self.template()

    # -- 上下文 ------------------------------------------------------------

    def portal(self):
        from bika.lims import api
        return api.get_portal()

    def site_path(self):
        return "/".join(self.portal().getPhysicalPath())

    def max_range_days(self):
        return MAX_RANGE_DAYS

    # -- 时间窗 ------------------------------------------------------------

    def _parse_date(self, value):
        if not value:
            return None
        try:
            return datetime.strptime(value.strip(), DATE_FMT)
        except Exception:
            return None

    def date_range(self):
        """解析起止日期，返回 (since, until, error)。

        规则（2026-08-31 定）：
          * 都不填 -> 最近 DEFAULT_DAYS 天
          * 只填起 -> 止 = 今天
          * 只填止 -> 起 = 止往前 MAX_RANGE_DAYS
          * 止日期**含当天**：SQL 用左闭右开，until = 止 + 1 天
          * 跨度 > MAX_RANGE_DAYS -> **拒绝**，不截断
        """
        form = self.request.form
        raw_from = form.get("date_from", "")
        raw_to = form.get("date_to", "")
        start = self._parse_date(raw_from)
        end = self._parse_date(raw_to)

        if raw_from and start is None:
            return None, None, _(u"Start date must be YYYY-MM-DD")
        if raw_to and end is None:
            return None, None, _(u"End date must be YYYY-MM-DD")

        today = datetime.now().replace(hour=0, minute=0, second=0,
                                       microsecond=0)
        if start is None and end is None:
            since = today - timedelta(days=DEFAULT_DAYS - 1)
            until = today + timedelta(days=1)
        elif end is None:
            since = start
            until = today + timedelta(days=1)
        elif start is None:
            since = end - timedelta(days=MAX_RANGE_DAYS)
            until = end + timedelta(days=1)      # 含当天
        else:
            since = start
            until = end + timedelta(days=1)      # 含当天

        if until <= since:
            return None, None, _(u"End date cannot be earlier than start date")
        span = (until - since).days
        if span > MAX_RANGE_DAYS:
            return None, None, _(
                u"Requested range is ${span} days, over the ${max} day limit "
                u"(about 6 months). Please query in shorter periods - the "
                u"range is NOT truncated automatically, so that you never "
                u"mistake a partial result for the whole.",
                mapping={"span": span, "max": MAX_RANGE_DAYS})
        return since, until, None

    def range_label(self):
        """页面上明示当前查询区间，分段查时才知道自己在看哪一段。"""
        since, until, err = self.date_range()
        if err:
            return u""
        last_day = until - timedelta(days=1)
        return u"%s ~ %s" % (since.strftime(DATE_FMT),
                             last_day.strftime(DATE_FMT))

    # -- 筛选项 ------------------------------------------------------------

    def filters(self):
        form = self.request.form
        return {
            "actor": (form.get("actor") or "").strip(),
            "portal_type": (form.get("portal_type") or "").strip(),
            "action": (form.get("action") or "").strip(),
            "keyword": (form.get("q") or "").strip(),
            "date_from": (form.get("date_from") or "").strip(),
            "date_to": (form.get("date_to") or "").strip(),
        }

    # -- 分页游标 ----------------------------------------------------------

    def _cursor(self):
        """游标形如 `<iso ts>|<id>`，放在 URL 里，无状态。"""
        raw = self.request.form.get("cursor") or ""
        if "|" not in raw:
            return None
        ts, _, ident = raw.partition("|")
        try:
            return (ts, int(ident))
        except Exception:
            return None

    def _backwards(self):
        return self.request.form.get("dir") == "prev"

    def _make_cursor(self, row):
        return "%s|%s" % (row["ts"].isoformat(), row["id"])

    # -- 数据 --------------------------------------------------------------

    def _load(self):
        if self._rows is not None:
            return
        self._rows = []
        since, until, err = self.date_range()
        if err:
            self.error = err
            return

        dsn = db.dsn_for(self.portal())
        if not dsn:
            self.error = _(u"Cannot reach the database, please contact an administrator")
            logger.error("auditjournal: no DSN for %s", self.site_path())
            return

        flt = self.filters()
        rows, has_more = db.query(
            dsn, self.site_path(), since, until,
            actor=flt["actor"] or None,
            portal_type=flt["portal_type"] or None,
            action=flt["action"] or None,
            keyword=flt["keyword"] or None,
            cursor=self._cursor(),
            backwards=self._backwards(),
            limit=PAGE_SIZE)
        self._has_more = has_more
        self._rows = self._drop_removed(rows, self.site_path())

    def rows(self):
        self._load()
        return self._rows

    def has_error(self):
        self._load()
        return self.error is not None

    def error_message(self):
        self._load()
        return self.error or u""

    def next_url(self):
        """下一页。没有更多就返回空串。"""
        self._load()
        if self._backwards():
            # 往回翻时，"下一页"总是存在（就是来处），用最后一行做游标
            pass
        elif not self._has_more or not self._rows:
            return ""
        if not self._rows:
            return ""
        return self._page_url(self._make_cursor(self._rows[-1]), "next")

    def prev_url(self):
        """上一页。第一页（无游标）时返回空串。"""
        self._load()
        if not self._cursor() or not self._rows:
            return ""
        return self._page_url(self._make_cursor(self._rows[0]), "prev")

    def first_url(self):
        return self._page_url("", "")

    def _page_url(self, cursor, direction):
        flt = self.filters()
        parts = []
        for key, value in (("date_from", flt["date_from"]),
                           ("date_to", flt["date_to"]),
                           ("actor", flt["actor"]),
                           ("portal_type", flt["portal_type"]),
                           ("action", flt["action"]),
                           ("q", flt["keyword"]),
                           ("cursor", cursor),
                           ("dir", direction)):
            if value:
                parts.append("%s=%s" % (key, _quote(value)))
        base = "%s/@@audit-journal" % self.portal().absolute_url()
        return base + ("?" + "&".join(parts) if parts else "")

    # -- 孤儿过滤（决策 D）--------------------------------------------------

    def _drop_removed(self, rows, site_path):
        mine = [r for r in rows if r.get("site_path", site_path) == site_path]
        uids = set(r["uid"] for r in mine if r.get("uid"))
        alive = self._resolve_uids(uids)
        kept = [r for r in mine if r.get("uid") in alive]
        removed = len(mine) - len(kept)
        if removed:
            logger.debug("auditjournal: hid %d row(s) whose object is gone",
                         removed)
        return kept

    def _resolve_uids(self, uids):
        """**一次** catalog 查询，判断哪些对象还在。不许 N+1。

        只返回"还活着"的 uid 集合，**不取 URL**：
        ★ `resolve_uid/<uid>` 这个 traverser 在本环境不存在 → 404（实测）；
        ★ `brain.getURL()` 返回的是**不带站点根**的 URL → 报错页（实测）。
        URL 改用表里的 `obj_path` 拼（见 `object_url`）。
        """
        if not uids:
            return set()
        from bika.lims import api
        catalog = api.get_tool("uid_catalog")
        brains = catalog(UID=list(uids))
        return set(brain.UID for brain in brains)

    # -- 渲染辅助 ----------------------------------------------------------

    def format_ts(self, value):
        if not value:
            return u""
        try:
            return value.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return u"%s" % value

    def object_url(self, row):
        """点对象 → 该对象的 Audit Log 页签。

        用表里的 `obj_path` 减去站点路径，接 `portal.absolute_url()`。
        两次拼错的教训见 `_resolve_uids`。
        """
        obj_path = row.get("obj_path") or ""
        site_path = self.site_path()
        if not obj_path.startswith(site_path):
            return ""
        return "%s%s/@@auditlog" % (self.portal().absolute_url(),
                                    obj_path[len(site_path):])

    def object_label(self, row):
        return row.get("obj_title") or row.get("obj_id") or row.get("uid") or u""


def _quote(value):
    from urllib import quote
    if isinstance(value, unicode):        # noqa: F821 (Py2)
        value = value.encode("utf-8")
    return quote(str(value), safe="")
