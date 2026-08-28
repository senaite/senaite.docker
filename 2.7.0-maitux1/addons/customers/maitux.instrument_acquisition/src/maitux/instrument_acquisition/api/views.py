# -*- coding: utf-8 -*-
import json
import logging

from bika.lims import api
from Products.Five import BrowserView
from plone.protect.interfaces import IDisableCSRFProtection
from zope.interface import alsoProvides

from maitux.instrument_acquisition import forwarder
from maitux.instrument_acquisition.services.phase1_targets import (
    PHASE1_INGEST_TOKEN,
)
from maitux.instrument_acquisition.services.session_store import ingest_event
from maitux.instrument_acquisition.services.session_store import (
    get_active_session,
)
from maitux.instrument_acquisition.services.session_store import (
    resolve_listening_worksheet_by_instrument,
)
from maitux.instrument_acquisition.services.session_store import (
    resolve_worksheet_by_session_id,
)
from maitux.instrument_acquisition.services import tcp_probe

logger = logging.getLogger("maitux.instrument_acquisition.api")

try:  # Python 2
    _TEXT = unicode
except NameError:  # Python 3
    _TEXT = str


def _json_safe(value):
    """递归把 str(bytes) 转 unicode，避免 py2 json.dumps UnicodeDecodeError

    py2 下 API 数据可能混入 utf-8 编码的 str（如仪器/模板标题），
    json.dumps(..., ensure_ascii=False) 遇到非 ASCII str 会尝试按 ascii
    解码而崩溃；统一转 unicode 后序列化。
    """
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, str):
        if isinstance(value, _TEXT):  # py3 str / py2 unicode：无需处理
            return value
        try:
            return value.decode("utf-8")
        except Exception:
            return value.decode("latin-1", "ignore")
    return value


def _json_response(request, data, status=200):
    """返回 JSON 响应。"""
    request.response.setHeader("Content-Type", "application/json; charset=utf-8")
    request.response.setHeader("Cache-Control", "no-store")
    request.response.setStatus(status)
    return json.dumps(_json_safe(data), ensure_ascii=False)


def _get_template_for_instrument(context, instrument_code):
    """按仪器标识（instrument_code）查找其 InstrumentParsingTemplate

    :returns: 模板对象；找不到返回 None
    """
    return tcp_probe.get_template_for_instrument(context, instrument_code)


def _verify_token(context, instrument_code, token):
    """校验采集端 Token（一个中转站一个 Token）

    优先按仪器模板上登记的 `agent_token` 校验；模板未配置时回退到
    固定共享 Token（兼容旧部署）。固定共享 Token 始终有效。
    """
    token = api.safe_unicode(token or u"").strip()
    if not token:
        return False
    # 固定共享 Token 始终有效（兼容旧版采集端）
    if token == PHASE1_INGEST_TOKEN:
        return True
    # 模板登记的 agent_token（一个中转站一个 Token，多台仪器可填相同值）
    template = _get_template_for_instrument(context, instrument_code)
    if template is not None:
        configured = api.safe_unicode(
            getattr(template, "agent_token", "") or u"").strip()
        if configured and token == configured:
            return True
    return False


def _json_response(request, data, status=200):
    """返回 JSON 响应。"""
    request.response.setHeader("Content-Type", "application/json; charset=utf-8")
    request.response.setHeader("Cache-Control", "no-store")
    request.response.setStatus(status)
    return json.dumps(data, ensure_ascii=False)


class InstrumentAcquisitionAPI(BrowserView):
    """仪器采集 API 基类。"""

    def __call__(self):
        alsoProvides(self.request, IDisableCSRFProtection)
        return self.handle_request()

    def handle_request(self):
        """处理请求，供子类重写。"""
        return _json_response(self.request, {
            "success": False,
            "message": "Not implemented",
        }, status=501)


class ForwardTestAPI(InstrumentAcquisitionAPI):
    """测试 HTTP 转发 API。"""

    def handle_request(self):
        """测试转发功能。"""
        uid = self.request.get("uid")
        if not uid:
            return _json_response(self.request, {
                "success": False,
                "message": "Missing template UID",
            }, status=400)

        try:
            template = api.get_object(uid)
        except Exception:
            return _json_response(self.request, {
                "success": False,
                "message": "Invalid template UID",
            }, status=404)

        if not api.is_object(template) or api.get_portal_type(template) != "InstrumentParsingTemplate":
            return _json_response(self.request, {
                "success": False,
                "message": "Not an InstrumentParsingTemplate",
            }, status=400)

        # 获取测试数据。
        test_raw = self.request.get("raw_data", "TEST_DATA")
        test_parsed = self.request.get("parsed_data", '{"test": "value"}')

        try:
            test_parsed = json.loads(test_parsed)
        except Exception:
            pass

        # 执行转发。
        data_forwarder = forwarder.DataForwarder(template)
        if not data_forwarder.is_enabled():
            return _json_response(self.request, {
                "success": False,
                "message": "HTTP forward is not enabled for this template",
                "details": {
                    "forward_enabled": getattr(template, "forward_enabled", False),
                    "forward_url": getattr(template, "forward_url", ""),
                },
            }, status=400)

        success, message = data_forwarder.forward(test_raw, test_parsed)
        last_result = data_forwarder.get_last_result() if hasattr(data_forwarder, "get_last_result") else {}

        return _json_response(self.request, {
            "success": success,
            "message": message,
            "attempts": last_result.get("attempts", 0),
            "status_code": last_result.get("status_code"),
            "test_data": {
                "raw": test_raw,
                "parsed": test_parsed,
            },
        })


class ForwardHistoryAPI(InstrumentAcquisitionAPI):
    """获取转发历史 API。"""

    def handle_request(self):
        """获取转发历史记录。"""
        uid = self.request.get("uid")
        if not uid:
            return _json_response(self.request, {
                "success": False,
                "message": "Missing template UID",
            }, status=400)

        data_forwarder = forwarder.get_forwarder(uid)
        if not data_forwarder:
            return _json_response(self.request, {
                "success": False,
                "message": "Forwarder not found",
            }, status=404)

        limit = int(self.request.get("limit", 10))
        history = data_forwarder.get_forward_history(limit=limit)

        queue_size = 0
        if hasattr(data_forwarder, "get_queue_size"):
            queue_size = data_forwarder.get_queue_size()

        return _json_response(self.request, {
            "success": True,
            "history": history,
            "queue_size": queue_size,
            "last_result": data_forwarder.get_last_result() if hasattr(data_forwarder, "get_last_result") else {},
        })


class ForwardStatusAPI(InstrumentAcquisitionAPI):
    """转发状态 API。"""

    def handle_request(self):
        """获取转发状态。"""
        uid = self.request.get("uid")
        if not uid:
            return _json_response(self.request, {
                "success": False,
                "message": "Missing template UID",
            }, status=400)

        try:
            template = api.get_object(uid)
        except Exception:
            return _json_response(self.request, {
                "success": False,
                "message": "Invalid template UID",
            }, status=404)

        if not api.is_object(template):
            return _json_response(self.request, {
                "success": False,
                "message": "Invalid template object",
            }, status=404)

        data_forwarder = forwarder.get_forwarder(uid)
        forwarder_status = {}
        if data_forwarder:
            forwarder_status = {
                "is_enabled": data_forwarder.is_enabled(),
                "queue_size": data_forwarder.get_queue_size() if hasattr(data_forwarder, "get_queue_size") else 0,
                "last_result": data_forwarder.get_last_result() if hasattr(data_forwarder, "get_last_result") else {},
            }

        return _json_response(self.request, {
            "success": True,
            "template": {
                "uid": api.get_uid(template),
                "title": api.get_title(template),
                "forward_enabled": getattr(template, "forward_enabled", False),
                "forward_url": getattr(template, "forward_url", ""),
                "forward_method": getattr(template, "forward_method", "POST"),
                "forward_timeout": getattr(template, "forward_timeout", 30),
            },
            "forwarder": forwarder_status,
        })


class TemplatesListAPI(InstrumentAcquisitionAPI):
    """获取模板列表 API。"""

    def handle_request(self):
        """获取所有仪器解析模板。"""
        results = api.search({
            "portal_type": "InstrumentParsingTemplate",
            "sort_on": "sortable_title",
            "sort_order": "ascending",
        }, catalog="senaite_catalog_setup")

        templates = []
        for brain in results:
            try:
                templates.append({
                    "uid": brain.UID,
                    "title": brain.Title,
                    "url": brain.getURL(),
                })
            except Exception:
                pass

        return _json_response(self.request, {
            "success": True,
            "templates": templates,
        })


class ManualForwardAPI(InstrumentAcquisitionAPI):
    """手动转发数据 API。"""

    def handle_request(self):
        """手动转发数据。"""
        if self.request.method != "POST":
            return _json_response(self.request, {
                "success": False,
                "message": "Method not allowed",
            }, status=405)

        uid = self.request.get("uid")
        if not uid:
            return _json_response(self.request, {
                "success": False,
                "message": "Missing template UID",
            }, status=400)

        try:
            template = api.get_object(uid)
        except Exception:
            return _json_response(self.request, {
                "success": False,
                "message": "Invalid template UID",
            }, status=404)

        if not api.is_object(template) or api.get_portal_type(template) != "InstrumentParsingTemplate":
            return _json_response(self.request, {
                "success": False,
                "message": "Not an InstrumentParsingTemplate",
            }, status=400)

        # 获取请求体数据。
        try:
            body = json.loads(self.request.get("BODY", "{}"))
        except Exception:
            body = {}

        raw_data = body.get("raw_data", "")
        parsed_data = body.get("parsed_data", raw_data)

        if not raw_data:
            return _json_response(self.request, {
                "success": False,
                "message": "Missing raw_data",
            }, status=400)

        # 执行转发。
        data_forwarder = forwarder.DataForwarder(template)
        success, message = data_forwarder.forward(raw_data, parsed_data)
        last_result = data_forwarder.get_last_result() if hasattr(data_forwarder, "get_last_result") else {}

        return _json_response(self.request, {
            "success": success,
            "message": message,
            "attempts": last_result.get("attempts", 0),
            "status_code": last_result.get("status_code"),
            "data": {
                "raw": raw_data,
                "parsed": parsed_data,
            },
        })


class IngestReadingAPI(InstrumentAcquisitionAPI):
    """中转站入站读数接口（第一阶段正式采集主链路）

    协议：
    - POST /@@instrument_acquisition_api_ingest
    - 请求头：Content-Type: application/json
              X-Instrument-Token: <固定共享 Token>
    - 请求体：{"event_id", "session_id"?, "instrument_code",
               "received_at", "raw_text", "parsed": {"value", "unit", "stable"}}

    规则：
    - 必须通过固定 token 验证
    - 必须携带 event_id
    - 会话归属两种方式：
        带 session_id → 按 session_id 反查活动会话
        不带 session_id → 按 instrument_code 归入该仪器当前监听会话
          （远端采集端模式约定：agent 无状态，不带 session_id 推送）
    - 会话仪器与会话内 instrument_code 不匹配返回 rejected
    - event_id 已存在返回 duplicate（幂等去重）
    - 入站成功后立即追加日志
    """

    def handle_request(self):
        if self.request.method != "POST":
            return _json_response(self.request, {
                "success": False,
                "status": "rejected",
                "message": "Method not allowed",
            }, status=405)

        # 读取请求体
        try:
            body = json.loads(self.request.get("BODY", "{}"))
        except Exception:
            body = {}
        if not isinstance(body, dict):
            body = {}

        event_id = api.safe_unicode(body.get("event_id", "")).strip()
        session_id = api.safe_unicode(body.get("session_id", "")).strip()
        instrument_code = api.safe_unicode(body.get("instrument_code", "")).strip()
        if not event_id:
            return _json_response(self.request, {
                "success": False,
                "status": "rejected",
                "message": "Missing event_id",
            }, status=400)

        # Token 校验：按仪器模板登记的 agent_token（一个中转站一个 Token）
        # 不带 instrument_code 时先按 session_id 反查仪器再校验
        token = self.request.getHeader("X-Instrument-Token", "")
        token_code = instrument_code
        if not token_code and session_id:
            ws = resolve_worksheet_by_session_id(self.context, session_id)
            if ws is not None:
                sess = get_active_session(ws)
                if sess is not None:
                    token_code = sess.get("instrument_code", "")
        if not _verify_token(self.context, token_code, token):
            return _json_response(self.request, {
                "success": False,
                "status": "rejected",
                "message": "Invalid token",
            }, status=401)

        parsed = body.get("parsed")
        if not isinstance(parsed, dict):
            parsed = {}
        raw_text = api.safe_unicode(body.get("raw_text", ""))
        parsed_value = api.safe_unicode(parsed.get("value", ""))
        unit = api.safe_unicode(parsed.get("unit", ""))
        received_at = api.safe_unicode(body.get("received_at", ""))

        # 会话归属：优先按 session_id；不带 session_id 时按 instrument_code
        # 归入该仪器当前监听会话（远端采集端约定）
        if not session_id:
            if not instrument_code:
                return _json_response(self.request, {
                    "success": False,
                    "status": "rejected",
                    "message": "Missing session_id or instrument_code",
                }, status=400)
            worksheet, listening_session = (
                resolve_listening_worksheet_by_instrument(
                    self.context, instrument_code))
            if worksheet is None:
                return _json_response(self.request, {
                    "success": False,
                    "status": "rejected",
                    "message": "No active listening session for "
                               "instrument_code %s" % instrument_code,
                }, status=404)
            session_id = listening_session["session_id"]

        # 按 session_id 反查 Worksheet
        worksheet = resolve_worksheet_by_session_id(self.context, session_id)
        if worksheet is None:
            return _json_response(self.request, {
                "success": False,
                "status": "rejected",
                "message": "No active session found for session_id",
            }, status=404)

        status, event = ingest_event(
            worksheet,
            event_id,
            session_id,
            instrument_code,
            raw_text,
            parsed_value=parsed_value,
            unit=unit,
            received_at=received_at,
            source="relay-http",
        )

        if status == "rejected":
            return _json_response(self.request, {
                "success": False,
                "status": "rejected",
                "message": "Session not active, not started (listening) or "
                           "instrument mismatch",
            }, status=409)

        if status == "duplicate":
            return _json_response(self.request, {
                "success": True,
                "status": "duplicate",
                "event_id": event_id,
                "session_id": session_id,
            })

        return _json_response(self.request, {
            "success": True,
            "status": "created",
            "event_id": event_id,
            "session_id": session_id,
        })


class AgentConfigAPI(InstrumentAcquisitionAPI):
    """采集端（agent）配置拉取接口 —— 与本地采集端联动的核心

    协议（约定见 agent 侧 cloud_sync.py）：
    - GET /@@instrument_acquisition_api_agent_config?instrument_code=xxx
    - 请求头：X-Instrument-Token: <固定共享 Token>
    - 返回：
        {"start": true, "ip": "...", "port": 9000,
         "session_id": "...", "operator": "..."}   # LIMS 已开始采集
        {"start": false}                            # 未采集 / 已停止

    行为：
    - LIMS 采集页点「开始采集」→ 该仪器会话 listening=True →
      本接口返回 start:true + 模板配置的仪器地址
    - LIMS 点「停止采集」/ 会话被挤掉 → 无监听会话 → start:false
    - 采集端轮询本接口后自行连接/断开仪器（无状态，不带 session_id 推送）
    """

    def handle_request(self):
        token = self.request.getHeader("X-Instrument-Token", "")

        instrument_code = api.safe_unicode(
            self.request.get("instrument_code", "")).strip()
        if not instrument_code:
            return _json_response(self.request, {
                "start": False,
                "error": "Missing instrument_code",
            }, status=400)

        # 按仪器模板登记的 agent_token 校验（一个中转站一个 Token）
        if not _verify_token(self.context, instrument_code, token):
            return _json_response(self.request, {
                "start": False,
                "error": "Invalid token",
            }, status=401)

        worksheet, session = resolve_listening_worksheet_by_instrument(
            self.context, instrument_code)
        if worksheet is None:
            return _json_response(self.request, {
                "start": False,
                # 诊断：为什么找不到监听会话（排查联动故障用）
                "reason": self._diagnose_no_listening(instrument_code),
            })

        host, port, _template_title = tcp_probe.get_instrument_tcp_address(
            worksheet)
        if not host or not port:
            return _json_response(self.request, {
                "start": False,
                "error": "Instrument TCP address not configured "
                         "(template ip_address/port empty)",
            })

        # 模板登记的采集端接口地址（与天平地址不同，供采集端核对/展示）
        agent_api_url = u""
        template = _get_template_for_instrument(self.context, instrument_code)
        if template is not None:
            agent_api_url = api.safe_unicode(
                getattr(template, "agent_api_url", "") or u"").strip()

        return _json_response(self.request, {
            "start": True,
            "ip": host,
            "port": int(port),
            "session_id": session.get("session_id", u""),
            "operator": (session.get("occupied_by")
                         or session.get("started_by") or u""),
            "agent_api_url": agent_api_url,
        })

    def _diagnose_no_listening(self, instrument_code):
        """诊断 start:false 的原因（排查联动故障）

        返回字符串原因，随 agent_config 响应返回；agent 的
        cloud_last_pull 会记录，便于定位：
        - portal unavailable      → _get_portal 失败（请求上下文问题）
        - session index empty     → 会话索引未持久化（多为 Zope 未重启/旧代码）
        - no index entry for X    → 索引里没有该仪器的会话
        - index entry not active  → 索引状态非 active
        - worksheet UID not resolved → worksheet_uid 反查对象失败
        - no active session       → worksheet 上无活动会话
        - session not listening   → 会话存在但 listening 不是 True（未开始采集/持久化丢失）
        """
        try:
            from maitux.instrument_acquisition.services import session_store
            portal = session_store._get_portal(self.context)
            if portal is None:
                return u"portal unavailable"
            index = session_store._get_session_index(self.context)
            if not index:
                return u"session index empty"
            matches = [sid for sid, info in index.items()
                       if info.get("instrument_code") == instrument_code]
            if not matches:
                # 常见原因：采集端 instrument_code 与 LIMS 仪器 ID 不一致，
                # 列出索引中已有的仪器 ID 帮助排查
                all_codes = sorted(set(
                    info.get("instrument_code", "")
                    for info in index.values() if info.get("instrument_code")))
                return u"no index entry for %s (索引中已有仪器 ID: %s)" % (
                    instrument_code, u", ".join(all_codes) or u"无")
            for sid in matches:
                info = index[sid]
                # 跳过已关闭的历史会话，只诊断 active 的（避免误报
                # "index entry not active" 掩盖真正的 active 会话问题）
                if info.get("status") != session_store.SESSION_ACTIVE:
                    continue
                ws = session_store.resolve_worksheet_by_session_id(
                    self.context, sid)
                if ws is None:
                    return u"worksheet UID %s not resolved" % (
                        info.get("worksheet_uid") or u"")
                sess = session_store.get_active_session(ws)
                if sess is None:
                    return u"no active session on worksheet (%s)" % sid[:8]
                if sess.get("listening") is not True:
                    return u"session %s not listening (listening=%s)" % (
                        sid[:8], sess.get("listening"))
            return u"active session exists but not listening"
        except Exception as exc:  # noqa: BLE001
            return u"diagnose error: %s" % exc


class AgentInstrumentsAPI(InstrumentAcquisitionAPI):
    """中转站仪器清单接口 —— agent 无需本地配置仪器信息

    协议：
    - GET /@@instrument_acquisition_api_agent_instruments
    - 请求头：X-Instrument-Token: <中转站 Token>
    - 返回：{"instruments": [
        {"code": "instrument-3", "start": true, "ip": "...", "port": 9000},
        {"code": "instrument-4", "start": false},
        ...]}

    行为：
    - 按 Token 反查所有 InstrumentParsingTemplate（模板 agent_token == Token；
      一个中转站一个 Token，多台仪器共用 → 返回该中转站负责的全部仪器）
    - 每台仪器：LIMS 有监听会话 → start:true + 模板 ip/port；否则 start:false
    - agent 据此自动连接/断开各仪器（无需配置 code/ip/port）
    """

    def handle_request(self):
        token = self.request.getHeader("X-Instrument-Token", "")

        templates = tcp_probe.get_templates_by_token(self.context, token)
        result = []
        for template in templates:
            try:
                instrument = template.getInstrument()
                if instrument is None:
                    continue
                code = api.get_id(instrument)
                worksheet, _session = (
                    resolve_listening_worksheet_by_instrument(
                        self.context, code))
                if worksheet is None:
                    result.append({"code": code, "start": False})
                    continue
                host, port, _title = (
                    tcp_probe.get_instrument_tcp_address(worksheet))
                if not host or not port:
                    result.append({"code": code, "start": False})
                    continue
                result.append({
                    "code": code,
                    "start": True,
                    "ip": host,
                    "port": int(port),
                })
            except Exception:
                continue

        return _json_response(self.request, {"instruments": result})

