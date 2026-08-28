# -*- coding: utf-8 -*-
"""仪器采集页面（第一阶段正式采集界面）

面向业务人员的独立采集页面，职责：
- 创建/恢复当前 Worksheet 的活动采集会话
- 展示中转站推送过来的原始读数（events）
- 展示可分配目标位（target_key 抽象）
- 支持一条读数分配给多个目标位、撤销分配、废弃读数
- 支持 T_name 目标位手工填写名称
- 统一保存回写（writeback.save）
- 展示完整操作日志

交互：
- 表单 POST 动作（start_listening/stop_listening/assign/unassign/discard/
  set_name/save/close_session）
- 点击「开始采集」后会话才进入监听状态，才接受中转站推送
- GET ?format=json 返回页面数据（供前端轮询）
"""

import json

from Products.Five import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from bika.lims import api

from maitux.instrument_acquisition.api.views import _json_safe

from maitux.instrument_acquisition.services.phase1_targets import (
    T_NAME_KEYWORD,
)
from maitux.instrument_acquisition.services.phase1_targets import (
    get_readonly_keywords,
)
from maitux.instrument_acquisition.services.session_store import (
    assign_reading,
)
from maitux.instrument_acquisition.services.session_store import (
    close_session,
)
from maitux.instrument_acquisition.services.session_store import (
    discard_reading,
)
from maitux.instrument_acquisition.services.session_store import (
    ensure_session,
)
from maitux.instrument_acquisition.services.session_store import (
    flush_relay_readings,
)
from maitux.instrument_acquisition.services.session_store import (
    get_page_data,
)
from maitux.instrument_acquisition.services.session_store import (
    get_relay_status,
)
from maitux.instrument_acquisition.services.session_store import (
    is_listening,
)
from maitux.instrument_acquisition.services.session_store import (
    set_manual_value,
)
from maitux.instrument_acquisition.services.session_store import (
    start_listening,
)
from maitux.instrument_acquisition.services.session_store import (
    stop_listening,
)
from maitux.instrument_acquisition.services.session_store import (
    add_target_row,
)
from maitux.instrument_acquisition.services.session_store import (
    remove_target_row,
)
from maitux.instrument_acquisition.services.session_store import (
    unassign_reading,
)
from maitux.instrument_acquisition.services.writeback import save

ACQUISITION_VIEW_NAME = "worksheet_instrument_acquisition"

# 允许的名称关键字（可手工填写）
MANUAL_NAME_KEYWORDS = (T_NAME_KEYWORD,)


class InstrumentAcquisitionView(BrowserView):
    """Worksheet 仪器采集视图"""

    template = ViewPageTemplateFile("templates/acquisition.pt")

    def __init__(self, context, request):
        super(InstrumentAcquisitionView, self).__init__(context, request)
        self._prepared = False
        self._session = None
        self._session_error = None
        self._data = None

    def __call__(self):
        action = api.safe_unicode(self.request.form.get("action", "")).strip()
        if action:
            self.handle_action(action)
            if self.request.get("format") == "json":
                return self.render_json()
            return self.request.response.redirect(self.get_view_url())

        if self.request.get("format") == "json":
            return self.render_json()

        return self.template()

    # ------------------------------------------------------------------
    # 动作处理
    # ------------------------------------------------------------------

    def handle_action(self, action):
        form = self.request.form
        if action == "assign":
            event_id = api.safe_unicode(form.get("event_id", "")).strip()
            target_key = api.safe_unicode(form.get("target_key", "")).strip()
            ok, message = assign_reading(self.context, event_id, target_key)
            self.add_status_message(message, "info" if ok else "warning")
        elif action == "unassign":
            target_key = api.safe_unicode(form.get("target_key", "")).strip()
            ok, message = unassign_reading(self.context, target_key)
            self.add_status_message(message, "info" if ok else "warning")
        elif action == "discard":
            event_id = api.safe_unicode(form.get("event_id", "")).strip()
            ok, message = discard_reading(self.context, event_id)
            self.add_status_message(message, "info" if ok else "warning")
        elif action == "set_name":
            target_key = api.safe_unicode(form.get("target_key", "")).strip()
            value = api.safe_unicode(form.get("value", ""))
            ok, message = set_manual_value(self.context, target_key, value)
            self.add_status_message(message, "info" if ok else "warning")
        elif action == "save":
            ok, message, details = save(self.context)
            self.add_status_message(message, "info" if ok else "warning")
        elif action == "start_listening":
            force = bool(self.request.form.get("force"))
            ok, message = start_listening(self.context, force=force)
            self.add_status_message(message, "info" if ok else "warning")
        elif action == "stop_listening":
            ok, message = stop_listening(self.context)
            self.add_status_message(message, "info" if ok else "warning")
        elif action == "close_session":
            close_session(self.context)
            self.add_status_message(u"采集会话已关闭。", "info")
        elif action == "add_target_row":
            # 数组字段按组添加（T_name + T_weight 同时加一行）
            analysis_uid = api.safe_unicode(
                form.get("analysis_uid", "")).strip()
            ok, message = add_target_row(self.context, analysis_uid)
            self.add_status_message(message, "info" if ok else "warning")
        elif action == "remove_target_row":
            target_key = api.safe_unicode(
                form.get("target_key", "")).strip()
            ok, message = remove_target_row(self.context, target_key)
            self.add_status_message(message, "info" if ok else "warning")
        elif action == "change_instrument":
            self.handle_change_instrument(form)
        else:
            self.add_status_message(u"未知操作：%s" % action, "warning")

    def handle_change_instrument(self, form):
        """在采集界面更换仪器：先停止采集，再切换 Worksheet 仪器"""
        uid = api.safe_unicode(form.get("instrument_uid", "")).strip()
        instrument = None
        if uid:
            try:
                instrument = api.get_object(uid)
            except Exception:
                instrument = None
        if not api.is_object(instrument):
            self.add_status_message(u"请选择要更换的仪器。", "warning")
            return

        # 正在采集中：先断开仪器并停止监听
        if is_listening(self.context):
            stop_listening(self.context)

        self.context.setInstrument(instrument)
        self.context.reindexObject()
        self.add_status_message(
            u"仪器已更换为 %s，会话将重新创建，请点击「开始采集」。"
            % api.safe_unicode(api.get_title(instrument)), "info")

    # ------------------------------------------------------------------
    # 渲染辅助
    # ------------------------------------------------------------------

    def get_view_url(self):
        return "{}/@@{}".format(
            self.context.absolute_url(), ACQUISITION_VIEW_NAME)

    def add_status_message(self, message, level="info"):
        try:
            self.context.plone_utils.addPortalMessage(message, level)
        except Exception:
            pass

    def render_json(self):
        """返回页面数据 JSON（供前端轮询）"""
        self.request.response.setHeader(
            "Content-Type", "application/json; charset=utf-8")
        self.request.response.setHeader("Cache-Control", "no-store")
        # 轮询时把进程内 relay 缓冲的读数写入会话（本请求线程执行，ZODB 安全）
        self.flush_readings()
        # _json_safe：py2 下递归转 unicode，避免含中文 str 导致序列化崩溃
        return json.dumps(_json_safe(self.get_data()), ensure_ascii=False)

    def flush_readings(self):
        """把 relay 队列中的读数入库"""
        try:
            flush_relay_readings(self.context)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 数据准备
    # ------------------------------------------------------------------

    def _prepare(self):
        """按需初始化一次：确保会话并加载页面数据"""
        if self._prepared:
            return
        self._prepared = True
        try:
            session, created = ensure_session(self.context)
            self._session = session
        except ValueError as exc:
            self._session_error = api.safe_unicode(exc)
        self._data = get_page_data(self.context)

    def get_data(self):
        """返回完整页面数据（dict，JSON 序列化友好）"""
        self._prepare()
        data = dict(self._data or {})
        data["session_error"] = self._session_error or u""
        data["readonly_keywords"] = get_readonly_keywords()
        data["manual_name_keywords"] = list(MANUAL_NAME_KEYWORDS)
        data["listening"] = self.is_listening()
        data["relay"] = self.get_relay_state()
        return data

    def get_relay_state(self):
        """返回中转/采集端状态（占用者 + 连接状态），供前端弹确认框与状态展示

        远端采集端模式下 LIMS 不直连仪器（relay 无连接）：
        - 占用者：按 instrument_code 跨 Worksheet 查监听会话（弹确认框用）
        - 连接状态：本会话监听中时，调用采集端 /api/state 查询其 TCP 连接
          是否成功（用户期望：仪器连不上时采集页能看到报错）

        返回 dict；无监听/无占用时字段为空但结构稳定。
        """
        try:
            if self._is_agent_mode():
                from maitux.instrument_acquisition.services import session_store
                instrument_code = self.get_instrument_code()
                occupant_ws, occupant_session = (
                    session_store.find_instrument_occupant(
                        self.context, instrument_code))
                result = {
                    "active": False,
                    "session_id": u"",
                    "operator": u"",
                    "instrument_connected": False,
                    "agent_online": False,
                    "agent_message": u"",
                }
                if occupant_ws is not None:
                    result["active"] = True
                    result["session_id"] = (
                        occupant_session.get("session_id", u"") or u"")
                    result["operator"] = (
                        occupant_session.get("occupied_by")
                        or occupant_session.get("started_by") or u"")
                # 本会话监听中：查采集端实际连接状态
                if self.is_listening():
                    agent_state = self._query_agent_state(instrument_code)
                    if agent_state is None:
                        result["agent_message"] = (
                            u"采集端不可达：请检查模板「采集端接口地址」与网络")
                    else:
                        result["agent_online"] = True
                        result["instrument_connected"] = bool(
                            agent_state.get("connected", False))
                        if result["instrument_connected"]:
                            result["agent_message"] = u"采集端已连接仪器"
                        else:
                            # 未连接：若 last_message 残留"已连接"（agent 停止
                            # 时未同步状态），显示明确的断开文案而非矛盾提示
                            last_msg = api.safe_unicode(
                                agent_state.get("last_message", u"")
                                or u"等待连接")
                            if u"已连接" in last_msg or u"连接成功" in last_msg:
                                result["agent_message"] = u"采集端连接已断开"
                            else:
                                result["agent_message"] = (
                                    u"采集端未连接：%s" % last_msg)
                # 未监听时 agent_message 保持为空，前端不显示状态徽章
                return result
            status = get_relay_status(self.context)
        except Exception:
            return None
        if not status:
            return None
        return {
            "active": bool(status.get("active", False)),
            "session_id": status.get("session_id", u"") or u"",
            "operator": status.get("operator", u"") or u"",
            "instrument_connected": bool(
                status.get("connected", False)),
        }

    def _query_agent_state(self, instrument_code):
        """调用采集端 /api/state 查询其 TCP 连接状态（远端采集端模式）

        地址取仪器模板的「采集端接口地址」（agent_api_url），与天平
        IP/端口分离；不可达或未配置时返回 None。
        """
        try:
            from maitux.instrument_acquisition.api.views import (
                _get_template_for_instrument,
            )
            template = _get_template_for_instrument(
                self.context, instrument_code)
            if template is None:
                return None
            agent_url = api.safe_unicode(
                getattr(template, "agent_api_url", "") or u"").strip()
            if not agent_url:
                return None
            # 带 code 查询：多仪器时返回该仪器的连接状态
            url = agent_url.rstrip("/") + "/api/state?code=" + \
                api.safe_unicode(instrument_code or u"")

            # py2 用 urllib2，py3 用 urllib.request（插件目标环境 py2）
            try:
                import urllib2
                opener = urllib2.build_opener(urllib2.ProxyHandler({}))
                response = opener.open(url, timeout=3)
                raw = response.read()
            except ImportError:  # Python 3
                import urllib.request
                response = urllib.request.urlopen(url, timeout=3)
                raw = response.read()
            return json.loads(raw.decode("utf-8", "ignore"))
        except Exception:
            return None

    def _is_agent_mode(self):
        """是否远端采集端模式（LIMS 不直连仪器，由本地采集端连接）"""
        try:
            from maitux.instrument_acquisition.services import phase1_targets
            return phase1_targets.PHASE1_AGENT_MODE
        except Exception:
            return False

    # ------------------------------------------------------------------
    # 模板数据访问
    # ------------------------------------------------------------------

    @property
    def session_info(self):
        self._prepare()
        return self._session or {}

    def get_session_id(self):
        return self.session_info.get("session_id", "")

    def get_session_status(self):
        return self.session_info.get("status", "")

    def is_listening(self):
        """当前会话是否处于监听状态（点击「开始采集」后为 True）"""
        try:
            return is_listening(self.context)
        except Exception:
            return False

    def get_session_error(self):
        return self._session_error or u""

    def has_session(self):
        return bool(self.get_session_id())

    def get_instrument_title(self):
        return self.session_info.get("instrument_title", "")

    def get_instrument_code(self):
        """返回会话仪器标识（入站接口 instrument_code 字段，联调用）"""
        return self.session_info.get("instrument_code", "")

    def getInstruments(self):
        """返回可更换的仪器下拉列表（DisplayList）"""
        from Products.Archetypes.public import DisplayList
        items = [("", u"— 选择仪器 —")]
        try:
            brains = api.search({
                "portal_type": "Instrument",
                "is_active": True,
                "sort_on": "sortable_title",
            }, catalog="senaite_catalog_setup")
            for brain in brains:
                items.append((brain.UID,
                              api.safe_unicode(brain.Title)))
        except Exception:
            pass
        # 当前仪器即使不在激活列表也保留显示
        current = None
        try:
            current = self.context.getInstrument()
        except Exception:
            current = None
        if current and api.get_uid(current) not in [i[0] for i in items]:
            items.append((api.get_uid(current),
                          api.safe_unicode(api.get_title(current))))
        return DisplayList(list(items))

    def get_current_instrument_uid(self):
        """返回 Worksheet 当前仪器 UID（下拉默认选中）"""
        try:
            instrument = self.context.getInstrument()
            if instrument:
                return api.get_uid(instrument)
        except Exception:
            pass
        return ""

    def get_worksheet_title(self):
        try:
            # py2 下 get_title 可能返回 str 中文，模板渲染会崩溃，统一转 unicode
            return api.safe_unicode(
                api.get_title(self.context) or api.get_id(self.context))
        except Exception:
            return u""

    def get_worksheet_url(self):
        return self.context.absolute_url()

    def get_manage_results_url(self):
        return "{}/manage_results".format(self.context.absolute_url())

    def get_readings(self):
        data = self.get_data()
        return data.get("readings", [])

    def get_targets(self):
        data = self.get_data()
        return data.get("targets", [])

    def get_logs(self):
        data = self.get_data()
        return data.get("logs", [])

    def get_counts(self):
        data = self.get_data()
        return data.get("counts", {})

    def get_readonly_keywords(self):
        return get_readonly_keywords()

    def is_manual_name_keyword(self, keyword):
        return keyword in MANUAL_NAME_KEYWORDS

    def get_reading_options(self):
        """返回可分配的读数下拉选项（pending/assigned 状态）"""
        options = []
        for reading in self.get_readings():
            status = reading.get("status")
            if status not in ("pending", "assigned"):
                continue
            label = u"#{} {} {}".format(
                reading.get("event_id", "")[:8],
                reading.get("parsed_value") or reading.get("raw_text"),
                reading.get("unit", ""))
            options.append({
                "event_id": reading.get("event_id", ""),
                "label": label,
            })
        return options

    def get_target_label(self, target):
        """目标位下拉显示文案（带组序号，如 "重量 · 重量 1"）

        row_title 含序号（重量 1/重量 2…），区分同分析项的多行；
        unicode 拼接，避免 py2 下 '·' 字面量崩溃。
        """
        return u"%s \u00b7 %s" % (
            api.safe_unicode(target.get("analysis_title") or u""),
            api.safe_unicode(target.get("row_title")
                             or target.get("display_title") or u""))

    def get_target_groups(self):
        """目标位按组（seq）分组（key-value 排版：名称+重量并排）"""
        try:
            from maitux.instrument_acquisition.services import session_store
            return session_store.build_target_groups(self.context)
        except Exception:
            return []

    def get_status_title(self, status):
        return {
            "pending": u"待分配",
            "assigned": u"已分配",
            "saved": u"已保存",
            "discarded": u"已废弃",
            "filled": u"已填写",
            "stale": u"已失效（旧会话）",
        }.get(status, status or u"")
