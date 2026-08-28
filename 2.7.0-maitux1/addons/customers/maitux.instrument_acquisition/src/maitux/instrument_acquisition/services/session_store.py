# -*- coding: utf-8 -*-
"""第一阶段采集会话、原始读数、分配与日志的 annotations 存储

第一阶段不在 ZODB 中新建 Dexterity content type，统一使用 Worksheet 的
annotations 持久化采集会话、原始读数、分配关系与操作日志：

    annotations[PHASE1_ANNOTATION_KEY] = {
        "active_session": {...},   # 当前活动会话
        "events": {event_id: {...}},      # 原始读数，按 event_id 幂等去重
        "assignments": {target_key: {...}},  # 目标位分配关系（target_key 抽象）
        "logs": [{...}],           # 完整业务日志
    }

跨 Worksheet 的会话反查（中转站按 session_id 找 Worksheet）通过 portal
annotations 上的会话索引 `PHASE1_SESSION_INDEX_KEY` 实现。
"""

import json
import logging
import uuid
from datetime import datetime

from bika.lims import api
from zope.annotation.interfaces import IAnnotations

from maitux.instrument_acquisition.services import relay
from maitux.instrument_acquisition.services import phase1_targets
from maitux.instrument_acquisition.services.phase1_targets import (
    PHASE1_ANNOTATION_KEY,
)
from maitux.instrument_acquisition.services.phase1_targets import (
    PHASE1_SESSION_INDEX_KEY,
)
from maitux.instrument_acquisition.services.phase1_targets import PHASE1_KEYWORDS
from maitux.instrument_acquisition.services.phase1_targets import (
    get_target_definitions,
)
from maitux.instrument_acquisition.services.phase1_targets import make_target_key
from maitux.instrument_acquisition.services.phase1_targets import parse_target_key
from maitux.instrument_acquisition.services.phase1_targets import (
    parse_target_key_full,
)
from maitux.instrument_acquisition.services.phase1_targets import (
    is_array_result_type,
)
from maitux.instrument_acquisition.services.phase1_targets import (
    TARGET_KEY_SEPARATOR,
)
from maitux.instrument_acquisition.services.tcp_probe import start_instrument
from maitux.instrument_acquisition.services.tcp_probe import stop_instrument
from maitux.instrument_acquisition.services.tcp_probe import (
    get_instrument_tcp_address,
)
from maitux.instrument_acquisition.services.tcp_probe import (
    get_template_for_instrument,
)

try:  # Python 2
    import urllib2

    def _http_post_json(url, body, timeout):
        request = urllib2.Request(
            url, data=body.encode("utf-8"),
            headers={"Content-Type": "application/json"})
        return urllib2.urlopen(request, timeout=timeout).read()
except ImportError:  # Python 3
    import urllib.request

    def _http_post_json(url, body, timeout):
        request = urllib.request.Request(
            url, data=body.encode("utf-8"),
            headers={"Content-Type": "application/json"})
        return urllib.request.urlopen(request, timeout=timeout).read()


def _notify_agent(agent_url, action, payload=None, timeout=8):
    """调用采集端（中转站）HTTP 接口（/api/start 或 /api/stop）

    点击「开始采集」时 LIMS 主动通知采集端立即连接仪器通道，连接失败
    由采集端同步返回，LIMS 据此报错（而不是等采集端轮询才发现）。

    :param agent_url: 采集端接口地址（模板 agent_api_url，与天平地址分离）
    :param action: 接口路径，如 "/api/start"、"/api/stop"
    :param payload: JSON 请求体
    :returns: (success, message)
    """
    agent_url = api.safe_unicode(agent_url or u"").strip()
    if not agent_url:
        return False, u"采集端接口地址未配置（模板「采集端接口地址」为空）"
    url = agent_url.rstrip("/") + action
    body = json.dumps(payload or {}, ensure_ascii=False)
    try:
        raw = _http_post_json(url, body, timeout)
        data = json.loads(raw.decode("utf-8", "ignore"))
    except Exception as exc:
        return False, u"无法连接采集端 %s：%s" % (url, exc)
    if data.get("success"):
        return True, api.safe_unicode(data.get("message") or u"")
    return False, api.safe_unicode(data.get("message") or u"采集端返回失败")

logger = logging.getLogger("maitux.instrument_acquisition")

# 读数状态
STATUS_PENDING = "pending"
STATUS_ASSIGNED = "assigned"
STATUS_SAVED = "saved"
STATUS_DISCARDED = "discarded"

# 会话状态
SESSION_ACTIVE = "active"
SESSION_CLOSED = "closed"

# 目标位分配来源
SOURCE_READING = "reading"
SOURCE_MANUAL = "manual"


def _now():
    """返回 ISO 格式当前时间"""
    return datetime.now().isoformat()


def _get_user_id():
    """返回当前登录用户 id，取不到时返回空字符串"""
    try:
        from bika.lims.api.user import get_user_id
        return api.safe_unicode(get_user_id() or u"")
    except Exception:
        return u""


def _get_user_name():
    """返回当前登录用户显示名（取不到时回退到用户 id）"""
    try:
        from bika.lims.api import get_user_fullname
        from bika.lims.api.user import get_user_id
        name = get_user_fullname(get_user_id())
        if name:
            return api.safe_unicode(name)
    except Exception:
        pass
    return _get_user_id()


def _get_portal(context):
    """返回 portal 对象；测试等无请求环境下返回 None"""
    try:
        return api.get_portal()
    except Exception:
        return None


def get_session_data(worksheet):
    """返回 Worksheet annotations 中的会话数据结构（惰性初始化）"""
    annotations = IAnnotations(worksheet)
    data = annotations.get(PHASE1_ANNOTATION_KEY)
    if data is None:
        data = {
            "active_session": None,
            "events": {},
            "assignments": {},
            "logs": [],
        }
        annotations[PHASE1_ANNOTATION_KEY] = data
        _mark_changed(worksheet)
    return data


def _commit(worksheet, data):
    """提交会话数据到 annotations

    zope.annotation 的 AttributeAnnotations.__setitem__ 只修改对象的
    __annotations__ dict，**不会把对象标记为 ZODB 脏**（_p_changed）——
    事务提交时只保存被标记脏的对象，不标记会导致跨请求丢失（表现为
    listening=True 等状态在下一个请求读不到）。这里显式标记脏。
    """
    IAnnotations(worksheet)[PHASE1_ANNOTATION_KEY] = data
    try:
        worksheet._p_changed = 1
    except Exception:
        pass


def _mark_changed(obj):
    """标记 ZODB Persistent 对象为脏（事务提交时持久化）"""
    try:
        obj._p_changed = 1
    except Exception:
        pass


def commit_session_data(worksheet, data):
    """公开提交接口：将修改后的会话数据写回 annotations

    供 session_store 之外的模块（如统一回写服务）在直接修改
    get_session_data 返回的数据结构后调用。
    """
    _commit(worksheet, data)


def _get_session_index(context):
    """返回 portal 上的会话索引 {session_id: info}（惰性初始化）"""
    portal = _get_portal(context)
    if portal is None:
        return {}
    annotations = IAnnotations(portal)
    index = annotations.get(PHASE1_SESSION_INDEX_KEY)
    if index is None:
        index = {}
        annotations[PHASE1_SESSION_INDEX_KEY] = index
        _mark_changed(portal)
    return index


def _commit_session_index(context):
    """提交会话索引到 portal annotations（保证跨请求持久化）"""
    portal = _get_portal(context)
    if portal is None:
        return
    IAnnotations(portal)[PHASE1_SESSION_INDEX_KEY] = _get_session_index(context)
    _mark_changed(portal)


def resolve_worksheet_by_session_id(context, session_id):
    """按 session_id 反查 Worksheet 对象，找不到返回 None"""
    if not session_id:
        return None
    index = _get_session_index(context)
    info = index.get(session_id)
    if not info:
        return None
    worksheet_uid = info.get("worksheet_uid")
    if not worksheet_uid:
        return None
    try:
        worksheet = api.get_object(worksheet_uid)
    except Exception:
        return None
    if not api.is_object(worksheet):
        return None
    return worksheet


def _iter_index_sessions_by_instrument(context, instrument_code):
    """按 instrument_code 扫描 portal 会话索引，产出 (worksheet, session)

    仅产出索引仍为 active 且 Worksheet 上活动会话与索引一致的有效条目。
    """
    if not instrument_code:
        return
    index = _get_session_index(context)
    for session_id, info in index.items():
        if info.get("instrument_code") != instrument_code:
            continue
        if info.get("status") != SESSION_ACTIVE:
            continue
        worksheet = resolve_worksheet_by_session_id(context, session_id)
        if worksheet is None:
            continue
        session = get_active_session(worksheet)
        if session is None:
            continue
        if session.get("session_id") != session_id:
            continue
        yield worksheet, session


def resolve_listening_worksheet_by_instrument(context, instrument_code):
    """按 instrument_code 找当前**正在监听**该仪器的活动会话

    供远端采集端（agent）配置接口使用：LIMS 点「开始采集」后置会话
    listening=True，采集端轮询本函数即可拿到应连接的仪器地址来源。

    :returns: (worksheet, session)；无监听会话时 (None, None)
    """
    for worksheet, session in _iter_index_sessions_by_instrument(
            context, instrument_code):
        if session.get("listening") is True:
            return worksheet, session
    return None, None


def find_instrument_occupant(worksheet, instrument_code, include_self=False):
    """按 instrument_code 找当前监听该仪器的**其他**会话（跨 Worksheet 互斥）

    远端采集端模式下，仪器占用不再由进程内 relay 连接承担（LIMS 不直连
    仪器），互斥改为按 instrument_code 扫描各 Worksheet 的监听会话：

    - 返回第一个监听该仪器的其他会话
    - include_self=True 时也允许命中本 Worksheet 自身（幂等重入判断）

    :returns: (occupant_worksheet, occupant_session)；无则 (None, None)
    """
    if not instrument_code:
        return None, None
    self_uid = api.get_uid(worksheet)
    for other_ws, session in _iter_index_sessions_by_instrument(
            worksheet, instrument_code):
        if api.get_uid(other_ws) == self_uid and not include_self:
            continue
        if session.get("listening") is not True:
            continue
        return other_ws, session
    return None, None


def _release_listening(worksheet, reason):
    """把某 Worksheet 的监听会话置为非监听并清空占用（挤占/关闭时调用）

    远端采集端模式下挤掉他人：对方会话 listening 置 False 后，其采集端
    下一轮轮询 agent_config 会拿到 start=false（或本仪器已由新会话接管）。
    """
    data = get_session_data(worksheet)
    session = data.get("active_session")
    if not session or session.get("status") != SESSION_ACTIVE:
        return False
    if session.get("listening", False) is not True:
        return False
    session["listening"] = False
    session["occupied_by"] = u""
    add_log(worksheet, "listen_preempted", api.safe_unicode(reason or u"会话被挤占"))
    _commit(worksheet, data)
    return True


def add_log(worksheet, action, message):
    """追加一条操作日志"""
    data = get_session_data(worksheet)
    logs = data.setdefault("logs", [])
    logs.append({
        "timestamp": _now(),
        "actor": _get_user_id(),
        "action": action,
        "message": api.safe_unicode(message),
    })
    _commit(worksheet, data)


def get_active_session(worksheet):
    """返回 Worksheet 当前活动会话，无则返回 None"""
    data = get_session_data(worksheet)
    session = data.get("active_session")
    if session and session.get("status") == SESSION_ACTIVE:
        return session
    return None


def ensure_session(worksheet, instrument=None):
    """确保 Worksheet 存在活动采集会话，返回 (session, created)

    - 已有活动会话且仪器与 Worksheet 当前仪器一致时直接恢复
    - Worksheet 仪器发生变更时，关闭旧会话并创建新会话（防止沿用旧仪器）
    - Worksheet 未分配仪器时抛出 ValueError

    注意：这里**不再**跨 Worksheet 强关同仪器的其他会话。仪器占用互斥由
    进程内 relay 服务在「开始采集」时负责（拒绝后来者/挤占确认），避免
    误关他人正在采集的会话。

    :param worksheet: Worksheet 对象
    :param instrument: 可选，显式指定仪器；缺省使用 worksheet.getInstrument()
    :returns: (session_dict, created_flag)
    """
    instrument = instrument or worksheet.getInstrument()
    if not api.is_object(instrument):
        raise ValueError(u"Worksheet 尚未分配仪器，无法开始仪器采集。")

    instrument_uid = api.get_uid(instrument)
    instrument_code = api.get_id(instrument)
    # py2 下 api.get_title 可能返回 str(bytes)，统一转 unicode 防 JSON 序列化崩溃
    instrument_title = api.safe_unicode(api.get_title(instrument))
    worksheet_uid = api.get_uid(worksheet)

    # 已有活动会话：仪器一致则恢复；仪器变更则关闭旧会话重建
    existing = get_active_session(worksheet)
    if existing is not None:
        if existing.get("instrument_uid") == instrument_uid:
            return existing, False
        _close_session_data(
            worksheet,
            reason=u"Worksheet 仪器由 %s 变更为 %s，旧会话关闭"
                   % (existing.get("instrument_title") or u"未知",
                      instrument_title),
        )
        existing = None

    session_id = uuid.uuid4().hex

    session = {
        "session_id": session_id,
        "worksheet_uid": worksheet_uid,
        "instrument_uid": instrument_uid,
        "instrument_code": instrument_code,
        "instrument_title": instrument_title,
        "started_by": _get_user_id(),
        "started_at": _now(),
        "status": SESSION_ACTIVE,
        # 是否处于监听状态：点击「开始采集」后为 True，才接受中转站推送
        "listening": False,
        # 当前占用该仪器的用户（开始采集时记录，停止时清空）
        "occupied_by": u"",
    }

    data = get_session_data(worksheet)
    data["active_session"] = session

    index = _get_session_index(worksheet)
    # 清理本 Worksheet 在索引中残留的 active 条目：
    # 并发请求（页面加载 + 轮询同时触发 ensure_session）可能创建多个
    # 会话导致索引漂移，agent_config 按 instrument_code 遍历时会遇到
    # 与 active_session 不匹配的旧条目而返回 start:false。
    # 走到创建新会话分支说明没有可复用的 active 会话，清理安全。
    for sid, info in list(index.items()):
        if (info.get("worksheet_uid") == worksheet_uid
                and info.get("status") == SESSION_ACTIVE):
            info["status"] = SESSION_CLOSED
    index[session_id] = {
        "worksheet_uid": worksheet_uid,
        "instrument_uid": instrument_uid,
        "instrument_code": instrument_code,
        "status": SESSION_ACTIVE,
    }

    add_log(worksheet, "session_start",
            u"创建活动采集会话 %s（仪器：%s）" % (session_id, instrument_title))
    logger.info("Instrument acquisition session %s started on %s",
                session_id, api.get_path(worksheet))
    _commit(worksheet, data)
    _commit_session_index(worksheet)
    return session, True


def _close_session_data(worksheet, reason=None):
    """将 Worksheet 的活动会话标记为已关闭（供内部关闭其他会话使用）"""
    data = get_session_data(worksheet)
    session = data.get("active_session")
    if not session or session.get("status") != SESSION_ACTIVE:
        return False
    session["status"] = SESSION_CLOSED
    session["closed_at"] = _now()
    session["listening"] = False
    if reason:
        session["closed_reason"] = api.safe_unicode(reason)
    index = _get_session_index(worksheet)
    info = index.get(session.get("session_id"))
    if info:
        info["status"] = SESSION_CLOSED
    add_log(worksheet, "session_close", api.safe_unicode(reason or u"会话已关闭"))
    _commit(worksheet, data)
    _commit_session_index(worksheet)
    return True


def close_session(worksheet):
    """关闭 Worksheet 当前活动会话，返回是否发生关闭"""
    data = get_session_data(worksheet)
    session = data.get("active_session")
    if not session or session.get("status") != SESSION_ACTIVE:
        return False
    return _close_session_data(worksheet, reason=u"手动关闭采集会话")


def is_listening(worksheet):
    """当前活动会话是否处于监听状态（开始采集后为 True）

    - 远端采集端模式（PHASE1_AGENT_MODE=True）：LIMS 不直连仪器，
      listening 标记即真实状态（挤占由 start_listening 同步置 False）
    - 进程内 relay 模式：同时校验 relay 的实际占用归属，
      会话被他人挤掉后视为失效。
    """
    session = get_active_session(worksheet)
    if session is None:
        return False
    if session.get("listening", False) is not True:
        return False
    if phase1_targets.PHASE1_AGENT_MODE:
        return True
    # 该会话是否仍占用着仪器（relay 多仪器管理，按 session 归属校验）
    return relay.is_active(session.get("session_id"))


def start_listening(worksheet, force=False):
    """开始采集：置会话为监听状态（采集端联动的入口）

    - 无活动会话时先自动创建会话
    - 已在监听状态时幂等返回成功（若已被他人挤掉则自动失效重来）
    - 仪器正被其他用户占用时：
        force=False → 拒绝（前端先弹确认框）
        force=True  → 挤掉当前占用者，绑定当前会话
    - 开始采集时记录当前占用者（occupied_by）

    两种模式：
    - 远端采集端模式（默认）：LIMS 只标记监听并做跨 Worksheet 占用互斥，
      **不**由 LIMS 直连仪器；本地采集端轮询 agent_config 后自行连接。
    - 进程内 relay 模式：由 LIMS 进程内 relay 连接仪器（实际 TCP 连接）。

    :returns: (success, message)
    """
    try:
        session, created = ensure_session(worksheet)
    except ValueError as exc:
        return False, api.safe_unicode(exc)

    if session.get("listening", False) is True:
        # 校验本会话是否仍占用仪器（可能已被其他用户挤掉）
        if phase1_targets.PHASE1_AGENT_MODE:
            occupant_ws, _occupant_session = find_instrument_occupant(
                worksheet, session.get("instrument_code"))
            still_owns = occupant_ws is None
        else:
            still_owns = relay.is_active(session.get("session_id"))
        if still_owns:
            return True, u"已处于监听状态"
        session["listening"] = False
        session["occupied_by"] = u""
        add_log(worksheet, "listen_preempted",
                u"本会话的仪器占用已被其他用户接管，重新发起开始采集")
        _commit(worksheet, get_session_data(worksheet))

    operator = _get_user_name()
    instrument_code = session.get("instrument_code")

    if phase1_targets.PHASE1_AGENT_MODE:
        # ---- 远端采集端模式：主动通知采集端连接仪器，失败立即报错 ----
        occupant_ws, occupant_session = find_instrument_occupant(
            worksheet, instrument_code)
        if occupant_ws is not None and not force:
            return False, (u"用户 %s 正在使用该仪器（会话 %s），"
                           u"如需使用请确认挤占"
                           % (occupant_session.get("occupied_by")
                              or occupant_session.get("started_by") or u"未知",
                              occupant_session.get("session_id", u"")))
        if occupant_ws is not None:
            # force：挤掉对方的监听会话（其采集端收到新开始指令后改连）
            _release_listening(
                occupant_ws,
                reason=u"仪器被用户 %s 挤占" % operator)
            logger.info(
                "Agent mode: session %s (user %s) preempted by %s",
                occupant_session.get("session_id"),
                occupant_session.get("occupied_by") or u"unknown",
                session.get("session_id"))

        # 仪器 TCP 地址来自解析模板（ip_address/port，天平地址）
        host, port, _template_title = get_instrument_tcp_address(worksheet)
        if not host or not port:
            return False, u"开始采集失败：仪器 TCP 地址未配置（模板 ip_address/port 为空）"

        # 采集端接口地址（agent_api_url，与天平地址分离）
        template = get_template_for_instrument(worksheet, instrument_code)
        agent_url = u""
        if template is not None:
            agent_url = api.safe_unicode(
                getattr(template, "agent_api_url", "") or u"").strip()

        # 主动调用采集端 /api/start_sync：同步尝试连接通道，失败返回报错
        ok_agent, agent_message = _notify_agent(
            agent_url, "/api/start_sync",
            {"code": instrument_code,
             "host": host, "port": int(port), "push": True})
        if not ok_agent:
            return False, u"开始采集失败：%s" % agent_message

        session["listening"] = True
        session["occupied_by"] = operator
        add_log(worksheet, "listen_start",
                u"开始采集，会话 %s 已通知采集端连接 %s:%s（用户 %s）"
                % (session.get("session_id"), host, port, operator))
        logger.info("Session %s started listening (agent mode)",
                    session.get("session_id"))
        _commit(worksheet, get_session_data(worksheet))
        return True, u"开始采集（采集端已连接 %s:%s）" % (host, port)

    # ---- 进程内 relay 模式：由 LIMS 直接连接仪器 ----
    ok_start, start_message = start_instrument(
        worksheet,
        session.get("session_id"),
        instrument_code,
        force=force,
        operator=operator,
    )
    if not ok_start:
        return False, u"开始采集失败：%s" % start_message

    session["listening"] = True
    session["occupied_by"] = operator
    add_log(worksheet, "listen_start",
            u"开始采集，会话 %s 开始监听（用户 %s，%s）"
            % (session.get("session_id"), operator, start_message))
    logger.info("Session %s started listening", session.get("session_id"))
    _commit(worksheet, get_session_data(worksheet))
    return True, u"开始采集（%s）" % start_message


def stop_listening(worksheet):
    """停止采集：置会话为非监听状态，并断开仪器（按模式）

    - 远端采集端模式：只置 listening=False，采集端轮询后自行断开
    - 进程内 relay 模式：通知 relay 断开仪器

    :returns: (success, message)
    """
    data = get_session_data(worksheet)
    session = data.get("active_session")
    if not session or session.get("status") != SESSION_ACTIVE:
        return False, u"当前没有活动采集会话"

    if session.get("listening", False) is not True:
        return True, u"已处于停止状态"

    if not phase1_targets.PHASE1_AGENT_MODE:
        # 进程内 relay 模式：断开仪器（失败不阻断本地状态更新）
        stop_instrument(session.get("session_id"))
    else:
        # 远端采集端模式：主动通知采集端断开连接
        instrument_code = session.get("instrument_code") or u""
        template = get_template_for_instrument(worksheet, instrument_code)
        agent_url = u""
        if template is not None:
            agent_url = api.safe_unicode(
                getattr(template, "agent_api_url", "") or u"").strip()
        ok_agent, agent_message = _notify_agent(
            agent_url, "/api/stop", {"code": instrument_code})
        if not ok_agent:
            add_log(worksheet, "listen_stop",
                    u"停止采集（采集端通知失败：%s）" % agent_message)

    session["listening"] = False
    session["occupied_by"] = u""
    add_log(worksheet, "listen_stop",
            u"停止采集，会话 %s 停止监听" % session.get("session_id"))
    logger.info("Session %s stopped listening", session.get("session_id"))
    _commit(worksheet, data)
    return True, u"停止采集"


def get_relay_status(worksheet):
    """查询当前 Worksheet 仪器在进程内 relay 的状态（占用者/连接），
    供采集页弹确认框判断该仪器是否被其他用户占用

    仪器地址未配置或 relay 无连接时返回 None。
    """
    try:
        from maitux.instrument_acquisition.services import tcp_probe
        host, port, _ = tcp_probe.get_instrument_tcp_address(worksheet)
        if not host or not port:
            return None
        return relay.status_for(host, port)
    except Exception:
        return None


# flush 写入失败后的最大重试次数（超过则丢弃并记录日志）
RELAY_FLUSH_MAX_RETRIES = 5


def flush_relay_readings(worksheet):
    """把进程内 relay 缓冲的读数写入当前会话（采集页轮询时调用）

    reader 线程只收数据入内存队列；入库在本请求线程执行，保证 ZODB 安全。

    逐条处理：单条写入失败（异常/被拒）时**重新入队**，下个轮询周期重试；
    超过 RELAY_FLUSH_MAX_RETRIES 仍失败的读数丢弃并记录日志，避免无限重试。

    :returns: 本次入库的读数条数
    """
    session = get_active_session(worksheet)
    if not session or session.get("listening") is not True:
        return 0
    session_id = session.get("session_id")
    instrument_code = session.get("instrument_code")

    count = 0
    failed = 0
    while True:
        item = relay.pop_queue_item(session_id)
        if item is None:
            break
        try:
            status, event = ingest_event(
                worksheet,
                "relay-%s" % uuid.uuid4().hex,
                session_id,
                instrument_code,
                item.get("raw_text", u""),
                parsed_value=item.get("value", u""),
                unit=item.get("unit", u""),
                received_at=item.get("received_at"),
                source="relay-internal",
            )
        except Exception as exc:
            logger.warning("Relay flush error: %s", exc)
            status = "error"

        if status == "created":
            count += 1
            continue

        # 写入失败：记录并重试（有上限）
        retries = item.get("retries", 0)
        failed += 1
        if retries >= RELAY_FLUSH_MAX_RETRIES:
            logger.warning(
                "Relay flush: dropping reading after %s retries: %r",
                retries, item.get("raw_text", u""))
            continue
        relay.requeue(session_id, item)

    if failed:
        logger.warning("Relay flush: %s ingested, %s failed/retrying "
                       "(session %s)", count, failed, session_id)
    return count


def ingest_event(worksheet, event_id, session_id, instrument_code,
                 raw_text, parsed_value=None, unit=None, received_at=None,
                 source="relay-http"):
    """写入一条原始读数，按 event_id 幂等去重

    :param worksheet: 通过 session_id 反查得到的 Worksheet 对象
    :param event_id: 中转站事件唯一 id（幂等键）
    :param session_id: 采集会话 id
    :param instrument_code: 仪器标识（与会话中的 instrument_code 比对）
    :param raw_text: 原始串口/报文文本（不可变，保留原始格式）
    :param parsed_value: 解析后的数值（字符串形式）
    :param unit: 单位（如 mg）
    :param received_at: 采集时间（ISO 字符串）
    :param source: 来源标识，默认 relay-http
    :returns: (status, event)
        status 取值：created | duplicate | rejected
    """
    data = get_session_data(worksheet)
    session = data.get("active_session")
    if not session or session.get("status") != SESSION_ACTIVE:
        return "rejected", None
    if session.get("session_id") != session_id:
        return "rejected", None
    if session.get("instrument_code") != instrument_code:
        return "rejected", None
    # 仅在「开始采集」后才接受推送
    if session.get("listening", False) is not True:
        return "rejected", None

    events = data.setdefault("events", {})
    if event_id in events:
        return "duplicate", events[event_id]

    event = {
        "event_id": event_id,
        "session_id": session_id,
        "raw_text": api.safe_unicode(raw_text),
        "parsed_value": api.safe_unicode(parsed_value or u""),
        "unit": api.safe_unicode(unit or u""),
        "received_at": api.safe_unicode(received_at or _now()),
        "source": source,
        "status": STATUS_PENDING,
        "targets": [],
    }
    events[event_id] = event
    add_log(worksheet, "receive",
            u"接收读数 %s（%s）" % (event_id, event["raw_text"]))
    logger.info("Reading %s ingested into session %s", event_id, session_id)
    _commit(worksheet, data)
    return "created", event


def assign_reading(worksheet, event_id, target_key):
    """将一条读数分配给一个目标位（一条读数可分配给多个目标位）

    :returns: (success, message)
    """
    data = get_session_data(worksheet)
    events = data.setdefault("events", {})
    event = events.get(event_id)
    if event is None:
        return False, u"读数不存在：%s" % event_id
    if event.get("status") == STATUS_DISCARDED:
        return False, u"已废弃的读数不能分配"
    if event.get("status") == STATUS_SAVED:
        return False, u"已保存的读数不能重新分配，请先撤销对应目标位"

    analysis_uid, keyword = parse_target_key(target_key)
    if not keyword or keyword not in PHASE1_KEYWORDS:
        return False, u"无效的目标位：%s" % target_key

    assignments = data.setdefault("assignments", {})
    existing = assignments.get(target_key)
    if existing and existing.get("event_id") and existing.get("event_id") != event_id:
        return False, u"目标位已被读数 %s 占用" % existing.get("event_id")

    assignments[target_key] = {
        "source": SOURCE_READING,
        "event_id": event_id,
        "assigned_by": _get_user_id(),
        "assigned_at": _now(),
    }
    targets = event.setdefault("targets", [])
    if target_key not in targets:
        targets.append(target_key)
    if event.get("status") == STATUS_PENDING:
        event["status"] = STATUS_ASSIGNED

    add_log(worksheet, "assign",
            u"读数 %s 分配到目标位 %s" % (event_id, target_key))
    _commit(worksheet, data)
    return True, u"分配成功"


def set_manual_value(worksheet, target_key, value):
    """为目标位设置手工填写值（第一阶段用于 T_name 名称字段）

    :returns: (success, message)
    """
    data = get_session_data(worksheet)
    analysis_uid, keyword = parse_target_key(target_key)
    if not keyword or keyword not in PHASE1_KEYWORDS:
        return False, u"无效的目标位：%s" % target_key

    assignments = data.setdefault("assignments", {})
    assignments[target_key] = {
        "source": SOURCE_MANUAL,
        "value": api.safe_unicode(value),
        "assigned_by": _get_user_id(),
        "assigned_at": _now(),
    }
    add_log(worksheet, "set_name",
            u"目标位 %s 手工填写值：%s" % (target_key, value or u"（空）"))
    _commit(worksheet, data)
    return True, u"已保存名称"


def unassign_reading(worksheet, target_key):
    """撤销目标位的分配，读数回到待分配状态（若不再被其他目标位引用）

    注意：**只清除绑定，不删除行**。数组字段（list 类型）的手动添加行
    靠 assignments 中的 ":seq" 键存在，若删除整个 assignment 会导致
    该行消失（页面只剩基础行）。撤销后保留空行（source=""），
    状态回到 pending，可重新绑定。

    :returns: (success, message)
    """
    data = get_session_data(worksheet)
    assignments = data.setdefault("assignments", {})
    assignment = assignments.get(target_key)

    # 回显行（无 assignment，值来自 analysis interim）：从 interim 移除
    # 已保存的值，行回到待绑定（pending）状态
    if not assignment:
        analysis_uid, keyword, seq = parse_target_key_full(target_key)
        if analysis_uid and seq > 0:
            # 撤销"已保存回显行"：创建空占位（组保留、不回显），
            # 回到 pending 可重新绑定；interim 旧值保留，重新保存时覆盖
            assignments[target_key] = {
                "source": "",
                "assigned_by": _get_user_id(),
                "assigned_at": _now(),
            }
            add_log(worksheet, "unassign",
                    u"撤销 %s 第 %s 组已保存值，可重新绑定" % (keyword, seq))
            _commit(worksheet, data)
            return True, u"已撤销，可重新绑定"
        return False, u"目标位 %s 未分配" % target_key

    event_id = assignment.get("event_id")
    # 清除绑定但保留行（数组字段额外行依赖 assignment 存在）
    assignment.pop("event_id", None)
    assignment["source"] = ""

    if event_id:
        event = data.get("events", {}).get(event_id)
        if event:
            targets = event.get("targets", [])
            if target_key in targets:
                targets.remove(target_key)
            if not targets and event.get("status") == STATUS_ASSIGNED:
                event["status"] = STATUS_PENDING

    add_log(worksheet, "unassign", u"撤销目标位 %s 的分配" % target_key)
    _commit(worksheet, data)
    return True, u"已撤销分配"


def discard_reading(worksheet, event_id):
    """废弃一条读数（终态，不可撤销），并释放其占用的目标位

    :returns: (success, message)
    """
    data = get_session_data(worksheet)
    events = data.setdefault("events", {})
    event = events.get(event_id)
    if event is None:
        return False, u"读数不存在：%s" % event_id
    if event.get("status") == STATUS_DISCARDED:
        return True, u"读数已废弃"
    if event.get("status") == STATUS_SAVED:
        return False, u"已保存的读数不能废弃，请先撤销对应目标位"

    assignments = data.setdefault("assignments", {})
    for target_key in list(event.get("targets", [])):
        if assignments.get(target_key, {}).get("event_id") == event_id:
            del assignments[target_key]
    event["targets"] = []
    event["status"] = STATUS_DISCARDED

    add_log(worksheet, "discard", u"废弃读数 %s（%s）" % (event_id, event["raw_text"]))
    _commit(worksheet, data)
    return True, u"已废弃"


def build_target_slots(worksheet, data=None):
    """生成第一阶段待分配目标位列表（target_key 抽象）

    目标位 = Worksheet 内所有分析行 × 该行支持的写死关键字（T_name/T_weight）。
    仅渲染分析行上确实存在对应 Interim Field 的目标位。

    :returns: 目标位字典列表
    """
    data = data or get_session_data(worksheet)
    assignments = data.get("assignments", {})
    events = data.get("events", {})
    definitions = get_target_definitions()
    definitions = sorted(definitions, key=lambda d: d.get("sort_order", 0))

    slots = []
    analyses = worksheet.getAnalyses() or []
    for analysis in analyses:
        analysis_uid = api.get_uid(analysis)
        # py2 下 api.get_title 可能返回 str(bytes) 中文，模板渲染会崩溃，统一转 unicode
        analysis_title = api.safe_unicode(
            api.get_title(analysis) or api.get_id(analysis))
        interims = analysis.getInterimFields() or []
        keywords = set()
        for interim in interims:
            keyword = interim.get("keyword")
            if keyword:
                keywords.add(keyword)
        # 各 interim 的 result_type（判断数组字段，支持添加行）
        interim_types = dict(
            (interim.get("keyword"), interim.get("result_type"))
            for interim in interims if interim.get("keyword"))

        # 先生成该分析项的所有行，再计算组锚点（"添加行"按钮位置）
        analysis_slots = []
        array_keywords = []
        for definition in definitions:
            keyword = definition.get("interim_keyword")
            if keyword not in keywords:
                continue
            is_array = is_array_result_type(interim_types.get(keyword))
            if is_array:
                array_keywords.append(keyword)

            # 基础行（seq=0）
            base_key = make_target_key(analysis_uid, keyword)
            analysis_slots.append(_build_slot(
                analysis, analysis_uid, analysis_title, keyword, definition,
                base_key, 0, assignments, events, is_array))
            # 数组字段的手动添加行：
            # - assignments 中带 :seq 的键（用户手动添加的行）
            # - interim 数组已保存的长度（保存回写后回显，无 assignment 也生成）
            if is_array:
                prefix = base_key + TARGET_KEY_SEPARATOR
                extra_seqs = set(
                    parse_target_key_full(key)[2]
                    for key in assignments
                    if key.startswith(prefix))
                saved_count = _interim_list_length(analysis, keyword)
                # interim 数组有 N 个值 = 组 seq 0..N-1；seq 0 是基础行，
                # 额外行只需 seq 1..N-1
                for seq in range(1, saved_count):
                    extra_seqs.add(seq)
                for seq in sorted(extra_seqs):
                    extra_key = make_target_key(analysis_uid, keyword, seq)
                    analysis_slots.append(_build_slot(
                        analysis, analysis_uid, analysis_title, keyword,
                        definition, extra_key, seq, assignments, events,
                        is_array))

        # 组锚点：数组字段组（如 T_name+T_weight）的最后一个字段的最后一行
        if array_keywords:
            # 组内定义顺序最后的字段（sort_order 最大）
            last_kw = max(
                array_keywords,
                key=lambda kw: next(
                    (d.get("sort_order", 0) for d in definitions
                     if d.get("interim_keyword") == kw), 0))
            # py2 的 max() 不支持 default 参数，手动求最大 seq
            max_seq = 0
            for s in analysis_slots:
                if s.get("is_array") and s.get("seq", 0) > max_seq:
                    max_seq = s.get("seq", 0)
            for s in analysis_slots:
                if (s.get("is_array") and s.get("interim_keyword") == last_kw
                        and s.get("seq") == max_seq):
                    s["is_add_row_anchor"] = True

        slots.extend(analysis_slots)

    slots.sort(key=lambda s: (s["sort_order"], s["analysis_title"],
                              s.get("seq", 0)))
    return slots


def build_target_groups(worksheet, data=None):
    """目标位按组（seq）分组：同一组的 T_name/T_weight 归为一组

    排版需求：T_name 与 T_weight 是绑定的 key-value 组，采集界面按组
    显示（第 1 组：名称 + 重量 并排），而不是按字段类型分开排列。

    :returns: 组列表，每组：
        {"seq", "analysis_uid", "analysis_title", "is_extra",
         "is_array", "is_add_row_anchor", "group_title",
         "slots": {keyword: slot}, "name_slot", "weight_slot"}
    """
    slots = build_target_slots(worksheet, data)
    groups = {}
    for slot in slots:
        key = (slot["analysis_uid"], slot.get("seq", 0))
        group = groups.get(key)
        if group is None:
            seq = slot.get("seq", 0)
            group = {
                "seq": seq,
                "analysis_uid": slot["analysis_uid"],
                "analysis_title": slot["analysis_title"],
                "is_extra": seq > 0,
                "is_array": slot.get("is_array", False),
                "is_add_row_anchor": False,
                "group_title": (u"第 %s 组" % (seq + 1) if seq
                                else u"第 1 组"),
                "slots": {},
            }
            groups[key] = group
        group["slots"][slot["interim_keyword"]] = slot
        if slot.get("is_add_row_anchor"):
            group["is_add_row_anchor"] = True

    result = sorted(groups.values(),
                    key=lambda g: (g["analysis_title"], g["seq"]))
    for group in result:
        slots_map = group["slots"]
        group["name_slot"] = slots_map.get("T_name")
        group["weight_slot"] = slots_map.get("T_weight")
        # 供模板遍历：按定义顺序排列的字段行
        group["field_slots"] = sorted(
            slots_map.values(),
            key=lambda s: s.get("sort_order", 0))
    return result


def _interim_list_length(analysis, keyword):
    """返回 analysis 数组 interim 已保存的值个数（保存回写后回显用）"""
    try:
        for interim in (analysis.getInterimFields() or []):
            if interim.get("keyword") != keyword:
                continue
            if not is_array_result_type(interim.get("result_type")):
                return 0
            value = interim.get("value")
            if value in (None, u"", ""):
                return 0
            try:
                values = json.loads(value)
                if isinstance(values, list):
                    return len(values)
            except Exception:
                return 1 if value else 0
            return 0
    except Exception:
        pass
    return 0


def _read_saved_interim(analysis, keyword, seq):
    """从分析项 interim 读取已保存的值（保存回写后的回显）

    数组字段（result_type=list 等）：value 为 JSON 数组字符串，取第 seq 个；
    非数组字段：seq=0 时返回单值。
    无值或取不到返回 None。
    """
    try:
        for interim in (analysis.getInterimFields() or []):
            if interim.get("keyword") != keyword:
                continue
            value = interim.get("value")
            if value in (None, u"", ""):
                return None
            if is_array_result_type(interim.get("result_type")):
                try:
                    values = json.loads(value)
                except Exception:
                    # 非 JSON（历史数据），按整串返回基础行
                    return (api.safe_unicode(value)
                            if seq == 0 else None)
                if isinstance(values, list) and seq < len(values):
                    return api.safe_unicode(values[seq])
                return None
            # 非数组
            return api.safe_unicode(value) if seq == 0 else None
    except Exception:
        return None
    return None


def _build_slot(analysis, analysis_uid, analysis_title, keyword, definition,
                target_key, seq, assignments, events, is_array=False):
    """构造单个目标位行（基础行 seq=0 / 手动添加行 seq>=1）

    无分配记录时回显 analysis interim 中已保存的值（status="saved"）。
    """
    assignment = assignments.get(target_key) or {}
    event = None
    value = None
    status = "pending"
    unit = u""
    if assignment.get("source") == SOURCE_MANUAL:
        value = assignment.get("value", "")
        status = "filled"
    elif assignment.get("event_id"):
        event = events.get(assignment.get("event_id"))
        if event:
            value = event.get("parsed_value") or event.get("raw_text")
            status = "assigned"
            unit = api.safe_unicode(event.get("unit") or u"")
        else:
            # 读数不属于当前会话（旧会话残留分配），标记为已失效
            status = "stale"
    if not assignment:
        # 无分配记录：保存回写后从 analysis interim 回显已保存的值
        # （有 assignment 的行——手动添加/已撤销——保持 pending 不回显）
        saved = _read_saved_interim(analysis, keyword, seq)
        if saved is not None:
            value = saved
            status = "saved"
    return {
        "target_key": target_key,
        "analysis_uid": analysis_uid,
        "analysis_title": analysis_title,
        "interim_keyword": keyword,
        "display_title": definition.get("display_title", keyword),
        "value_type": definition.get("value_type", "string"),
        "allow_multi_assign": definition.get("allow_multi_assign", False),
        "sort_order": definition.get("sort_order", 0),
        "seq": seq,
        "is_extra": seq > 0,
        "is_array": bool(is_array),
        "is_add_row_anchor": False,
        "row_title": (u"%s %s" % (definition.get("display_title", keyword),
                                   seq + 1)
                      if seq else definition.get("display_title", keyword)),
        "status": status,
        "value": value,
        "unit": unit,
        "source_event_id": assignment.get("event_id", ""),
        "assignment": assignment,
    }


def get_array_keywords(analysis):
    """返回分析项的数组类型字段关键字（result_type 为 list/multiselect 等）"""
    keywords = []
    for interim in (analysis.getInterimFields() or []):
        keyword = interim.get("keyword")
        if keyword in PHASE1_KEYWORDS and is_array_result_type(
                interim.get("result_type")):
            keywords.append(keyword)
    return keywords


def _remove_saved_interim(analysis, keyword, seq):
    """从 analysis 数组 interim 移除第 seq 个已保存的值

    删除/撤销"已保存回显行"时调用：清理 interim 数组对应元素，
    避免下次进入采集界面时该行回显恢复。
    """
    try:
        interims = analysis.getInterimFields() or []
        for interim in interims:
            if interim.get("keyword") != keyword:
                continue
            value = interim.get("value")
            if value in (None, u"", ""):
                return False
            try:
                values = json.loads(value)
            except Exception:
                return False
            if not isinstance(values, list) or seq >= len(values):
                return False
            values.pop(seq)
            interim["value"] = json.dumps(values, ensure_ascii=False)
            analysis.setInterimFields(interims)
            analysis.reindexObject()
            return True
    except Exception:
        pass
    return False


def add_target_row(worksheet, analysis_uid):
    """数组字段手动添加一组目标位行（如 T_name + T_weight 同时加一行）

    :returns: (success, message)
    """
    try:
        analysis = api.get_object(analysis_uid)
    except Exception:
        analysis = None
    if not api.is_object(analysis):
        return False, u"无效的分析项"

    # 该分析项的数组字段组（T_name + T_weight 等）
    array_keywords = get_array_keywords(analysis)
    if not array_keywords:
        return False, u"该分析项没有数组类型字段，无需添加行"

    data = get_session_data(worksheet)
    assignments = data.setdefault("assignments", {})
    # 组内当前最大 seq：
    # - assignments 中带 :seq 的键（手动添加的行）
    # - 保存回显的行（interim 数组长度，无 assignment 也要算）
    seqs = [0]
    for key in assignments:
        _uid, _kw, s = parse_target_key_full(key)
        if (_uid == analysis_uid and _kw in array_keywords
                and s and s > 0):
            seqs.append(s)
    saved_count = _interim_list_length(analysis, array_keywords[0])
    if saved_count > 0:
        seqs.append(saved_count - 1)
    new_seq = max(seqs) + 1

    # 为组内每个数组字段添加一行（同一 seq，成组）
    for keyword in array_keywords:
        new_key = make_target_key(analysis_uid, keyword, new_seq)
        assignments[new_key] = {
            "source": "",
            "assigned_by": _get_user_id(),
            "assigned_at": _now(),
        }
    add_log(worksheet, "add_row",
            u"为 %s 添加第 %s 组数据（%s）" % (
                analysis_title_of(analysis), new_seq,
                u"、".join(array_keywords)))
    _commit(worksheet, data)
    return True, u"已添加第 %s 组数据" % new_seq


def analysis_title_of(analysis):
    """返回分析项标题（unicode，供日志等使用）"""
    try:
        return api.safe_unicode(api.get_title(analysis)
                                or api.get_id(analysis))
    except Exception:
        return u""


def remove_target_row(worksheet, target_key):
    """删除数组字段的手动添加行（按组删除：同序号的 T_name+T_weight 一起删）

    兼容"已保存回显行"（无 assignment、值来自 analysis interim）：
    同时从 interim 数组移除对应元素，避免再次进入时回显恢复。

    :returns: (success, message)
    """
    analysis_uid, keyword, seq = parse_target_key_full(target_key)
    if not analysis_uid or not keyword:
        return False, u"无效的目标位"
    if seq <= 0:
        return False, u"基础行不能删除"

    data = get_session_data(worksheet)
    assignments = data.get("assignments", {})
    events = data.setdefault("events", {})

    # 该分析项的数组字段组，删除同 seq 的所有字段行
    try:
        analysis = api.get_object(analysis_uid)
        if api.is_object(analysis):
            array_keywords = get_array_keywords(analysis)
        else:
            analysis = None
            array_keywords = [keyword]
    except Exception:
        analysis = None
        array_keywords = [keyword]

    removed = []
    for kw in array_keywords:
        key = make_target_key(analysis_uid, kw, seq)
        assignment = assignments.get(key)
        if assignment:
            # 释放绑定读数
            event_id = assignment.get("event_id")
            if event_id:
                event = events.get(event_id)
                if event:
                    targets = event.get("targets", [])
                    if key in targets:
                        targets.remove(key)
                    if not targets and event.get("status") == STATUS_ASSIGNED:
                        event["status"] = STATUS_PENDING
            del assignments[key]
            removed.append(kw)
        # 从 interim 移除已保存的值（回显行/保存数据清理）
        if analysis is not None:
            _remove_saved_interim(analysis, kw, seq)

    if not removed and analysis is None:
        return False, u"行不存在或已删除"

    add_log(worksheet, "remove_row",
            u"删除 %s 的第 %s 组数据" % (keyword, seq))
    _commit(worksheet, data)
    return True, u"已删除第 %s 组数据" % seq


def get_page_data(worksheet):
    """返回采集页面展示数据（JSON 序列化友好）

    只展示**当前活动会话**的读数：Worksheet 仪器变更重建会话后，
    旧会话的读数不混入新会话列表（数据保留在 annotations 中用于审计）。
    """
    data = get_session_data(worksheet)
    session = data.get("active_session") or {}
    session_id = session.get("session_id")
    events = data.get("events", {})
    assignments = data.get("assignments", {})

    # 仅保留当前会话的读数
    current_events = {}
    for event_id, event in events.items():
        if session_id and event.get("session_id") != session_id:
            continue
        current_events[event_id] = event

    readings = []
    for event_id in sorted(current_events.keys()):
        event = current_events[event_id]
        readings.append({
            "event_id": event_id,
            "raw_text": event.get("raw_text", ""),
            "parsed_value": event.get("parsed_value", ""),
            "unit": event.get("unit", ""),
            "received_at": event.get("received_at", ""),
            "status": event.get("status", ""),
            "targets": list(event.get("targets", [])),
        })

    # 目标位列表同样基于当前会话的读数解析（旧会话分配显示为空）
    filtered_data = dict(data)
    filtered_data["events"] = current_events
    targets = build_target_slots(worksheet, filtered_data)

    counts = {
        "total": len(current_events),
        "pending": sum(1 for e in current_events.values()
                       if e.get("status") == STATUS_PENDING),
        "assigned": sum(1 for e in current_events.values()
                        if e.get("status") == STATUS_ASSIGNED),
        "saved": sum(1 for e in current_events.values()
                     if e.get("status") == STATUS_SAVED),
        "discarded": sum(1 for e in current_events.values()
                         if e.get("status") == STATUS_DISCARDED),
    }

    return {
        "session": session,
        "readings": readings,
        "targets": targets,
        "assignments": assignments,
        "logs": list(data.get("logs", [])),
        "counts": counts,
    }
