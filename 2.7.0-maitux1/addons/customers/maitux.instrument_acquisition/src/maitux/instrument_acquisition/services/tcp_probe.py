# -*- coding: utf-8 -*-
"""第一阶段仪器连接客户端（进程内中转站）

第一阶段「开始采集」的仪器连接由 LIMS 进程内的 relay 服务负责
（`services/relay.py`），LIMS 不再直接 socket 探测仪器、也不再调用独立
中转站的 HTTP 接口：

- relay_start(...)：开始采集/连接仪器（互斥/挤占）
- relay_stop(...)：停止采集/断开仪器
- relay_status()：查询当前占用状态

仪器地址来源：`InstrumentParsingTemplate` 的 `ip_address` / `port` 字段，
由 LIMS 读取后交给 relay 服务。

保留 `probe_tcp` 纯 socket 探测函数，供单元测试与独立诊断使用。
"""

import logging
import socket

logger = logging.getLogger("maitux.instrument_acquisition")

try:
    from maitux.instrument_acquisition.services import relay
except Exception:  # pragma: no cover
    relay = None

try:
    from bika.lims import api
except ImportError:  # pragma: no cover
    api = None

try:
    from maitux.instrument_acquisition.services.phase1_targets import (
        PHASE1_TCP_PROBE_TIMEOUT,
    )
except Exception:  # pragma: no cover
    PHASE1_TCP_PROBE_TIMEOUT = 3

try:
    from maitux.instrument_acquisition.extender.instrument import FIELD_NAME
except Exception:  # pragma: no cover
    FIELD_NAME = "InstrumentAcquisitionTemplate"


def relay_start(session_id, instrument_code, host, port,
                force=False, operator=u""):
    """开始采集：连接仪器并占用（进程内 relay 服务）

    :param force: True 时挤掉当前占用者（LIMS 端已弹确认框）
    :param operator: 当前操作用户（显示名），记录占用者

    :returns: (success, message)
    """
    if relay is None:
        return False, u"进程内中转站服务不可用"
    return relay.start(
        session_id, instrument_code, host, port,
        operator=operator, force=force)


def relay_stop(session_id):
    """停止采集：断开仪器并释放占用

    :returns: (success, message)
    """
    if relay is None:
        return False, u"进程内中转站服务不可用"
    ok = relay.stop(session_id)
    return ok, (u"已停止采集" if ok else u"会话不存在或已释放")


def relay_status():
    """查询当前占用状态（进程内 relay 服务）"""
    if relay is None:
        return None
    return relay.get_status()


def probe_tcp(host, port, timeout=PHASE1_TCP_PROBE_TIMEOUT):
    """探测 TCP 端口是否可连接（纯 socket，用于单元测试/独立诊断）

    :returns: (success, message)
    """
    host = (host or u"").strip()
    if not host:
        return False, u"仪器 TCP 地址（ip_address）未配置"

    try:
        port = int(port)
    except (TypeError, ValueError):
        return False, u"仪器 TCP 端口配置无效：%s" % (port,)

    if port < 1 or port > 65535:
        return False, u"仪器 TCP 端口超出范围：%s" % (port,)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((host, port))
    except socket.timeout:
        return False, u"连接 %s:%s 超时（%s 秒）" % (host, port, timeout)
    except socket.gaierror as exc:
        return False, u"无法解析主机 %s：%s" % (host, exc)
    except socket.error as exc:
        return False, u"无法连接 %s:%s：%s" % (host, port, exc)
    except Exception as exc:  # pragma: no cover
        return False, u"连接 %s:%s 失败：%s" % (host, port, exc)
    finally:
        try:
            sock.close()
        except Exception:  # pragma: no cover
            pass

    return True, u"TCP 连接成功：%s:%s" % (host, port)


def _get_parsing_template(worksheet):
    """返回 Worksheet 仪器绑定的解析模板（ip_address/port 来源）"""
    try:
        instrument = worksheet.getInstrument()
        if not api.is_object(instrument):
            return None

        field = getattr(instrument, "getField", lambda *a, **k: None)(FIELD_NAME)
        if field is not None:
            try:
                template = field.get(instrument)
                if api.is_object(template):
                    return template
            except Exception:
                pass

        instrument_uid = api.get_uid(instrument)
        brains = api.search({
            "portal_type": "InstrumentParsingTemplate",
            "sort_on": "sortable_title",
            "sort_order": "ascending",
        }, catalog="senaite_catalog_setup")
        for brain in brains:
            try:
                template = api.get_object(brain)
                linked = getattr(template, "getInstrument", lambda: None)()
                if api.is_object(linked) and api.get_uid(linked) == instrument_uid:
                    return template
            except Exception:
                continue
    except Exception:
        logger.warning("Failed to resolve parsing template for relay", exc_info=True)
    return None


def get_template_for_instrument(context, instrument_code):
    """按仪器标识（instrument_code）查找其 InstrumentParsingTemplate

    agent_api_url / agent_token 等采集端配置字段来源。

    :returns: 模板对象；找不到返回 None
    """
    if not instrument_code:
        return None
    try:
        results = api.search({
            "portal_type": "InstrumentParsingTemplate",
            "is_active": True,
            "sort_on": "sortable_title",
            "sort_order": "ascending",
        }, catalog="senaite_catalog_setup")
    except Exception:
        return None
    for brain in results:
        try:
            template = api.get_object(brain)
            instrument = template.getInstrument()
            if instrument is None:
                continue
            if api.get_id(instrument) == instrument_code:
                return template
        except Exception:
            continue
    return None


def get_templates_by_token(context, token):
    """按采集端 Token 反查所有关联的 InstrumentParsingTemplate

    一个中转站一个 Token（多台仪器共用同一 Token），LIMS 据此返回该
    中转站负责的全部仪器（code/ip/port），agent 无需本地配置仪器信息。

    :returns: 模板对象列表
    """
    token = api.safe_unicode(token or u"").strip()
    if not token:
        return []
    try:
        results = api.search({
            "portal_type": "InstrumentParsingTemplate",
            "is_active": True,
            "sort_on": "sortable_title",
            "sort_order": "ascending",
        }, catalog="senaite_catalog_setup")
    except Exception:
        return []
    templates = []
    for brain in results:
        try:
            template = api.get_object(brain)
            configured = api.safe_unicode(
                getattr(template, "agent_token", "") or u"").strip()
            if configured and configured == token:
                templates.append(template)
        except Exception:
            continue
    return templates


def get_instrument_tcp_address(worksheet):
    """返回 (host, port, template_title)；未配置时返回 (None, None, "")"""
    template = _get_parsing_template(worksheet)
    if template is None:
        return None, None, u""
    host = api.safe_unicode(getattr(template, "ip_address", "") or u"").strip()
    port = api.safe_unicode(getattr(template, "port", "") or u"").strip()
    title = api.safe_unicode(api.get_title(template) or u"")
    return host, port, title


def start_instrument(worksheet, session_id, instrument_code,
                     force=False, operator=u""):
    """开始采集：读仪器地址 → 通知进程内 relay 服务连接仪器

    :param force: True 时挤掉当前占用者
    :param operator: 当前操作用户显示名（记录占用者）

    :returns: (success, message)
        - 仪器地址未配置：返回 (False, 提示)
        - 连接失败/占用：返回 (False, 原因)
        - 连接成功：返回 (True, 成功信息)
    """
    host, port, template_title = get_instrument_tcp_address(worksheet)
    if not host or not port:
        return False, u"仪器 TCP 地址未配置（模板 ip_address/port 为空）"

    success, message = relay_start(
        session_id, instrument_code, host, port,
        force=force, operator=operator)
    if not success:
        logger.warning("Relay start failed: %s", message)
        return False, message
    return True, message


def stop_instrument(session_id):
    """停止采集：通知进程内 relay 服务断开仪器"""
    success, message = relay_stop(session_id)
    return success, message
