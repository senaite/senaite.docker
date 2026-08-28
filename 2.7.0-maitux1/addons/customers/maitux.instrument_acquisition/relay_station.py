# -*- coding: utf-8 -*-
"""仪器采集中转站服务（第一阶段）

常驻 HTTP 服务，职责：
1. 接收 LIMS 的"开始/停止采集"指令，负责实际 TCP 连接仪器
2. 把仪器读数解析后 HTTP POST 给 LIMS 入站接口
3. 单仪器互斥：同一时刻只允许一个会话占用仪器（避免两个用户同时用一台仪器）

数据流：
    天平 ──串口──▶ W610(TCP Server) ◀── 本服务(TCP Client) ──HTTP POST──▶ LIMS

接口（供 LIMS 调用）：
    GET  /status   查询当前状态
    POST /start    开始采集：{"session_id", "instrument_code", "host", "port"}
    POST /stop     停止采集：{"session_id"}

仪器 IP 由 LIMS 在 /start 时传入（LIMS 从解析模板 ip_address/port 读取），
本服务不手动配置仪器地址。

零依赖（纯标准库），Python 2.7 / 3.x 均可运行。

用法：
    python relay_station.py --listen-port 9000 \
        --lims-url http://192.168.1.18:8080 \
        --token maitux-phase1-instrument-acquisition-token
"""

import argparse
import json
import re
import socket
import sys
import threading
import time
import uuid
from datetime import datetime

try:
    from http.server import BaseHTTPRequestHandler
    from http.server import ThreadingHTTPServer as HTTPServer
except ImportError:  # Python 2
    from BaseHTTPServer import BaseHTTPRequestHandler
    from BaseHTTPServer import HTTPServer

try:
    import urllib.request as urllib_request
    import urllib.error as urllib_error
except ImportError:  # Python 2
    import urllib2 as urllib_request
    import urllib2 as urllib_error

try:
    text_type = unicode
except NameError:  # Python 3
    text_type = str


DEFAULTS = {
    "listen_host": "0.0.0.0",
    "listen_port": 9000,
    "lims_url": "http://192.168.1.18:8080",
    "token": "maitux-phase1-instrument-acquisition-token",
    "connect_timeout": 3,       # 开始采集时连接仪器的超时（秒）
    "reconnect_delay": 3,       # 断线后重连间隔（秒）
}


# ----------------------------------------------------------------------
# 全局状态（单仪器，一个中转站实例管一台仪器）
# ----------------------------------------------------------------------
STATE = {
    "active": False,
    "session_id": "",
    "instrument_code": "",
    "instrument_host": "",
    "instrument_port": 0,
    "operator": u"",            # 当前占用该仪器的用户（开始采集时记录）
    "connected": False,
    "last_message": u"",
}
LOCK = threading.Lock()

CONFIG = dict(DEFAULTS)


def now_iso():
    return datetime.now().isoformat()


def log(message):
    print("[%s] %s" % (now_iso()[11:19], message))


# ----------------------------------------------------------------------
# 解析 + 推送
# ----------------------------------------------------------------------
def parse_reading(line):
    """从天平原生输出中提取 数值 + 单位（第一阶段通用启发式）"""
    value = ""
    unit = ""
    match = re.search(r"-?\d+(?:\.\d+)?", line)
    if match:
        value = match.group(0)
        rest = line[match.end():]
        unit_match = re.search(r"([a-zA-Z\u00b5/%]+)", rest)
        if unit_match:
            unit = unit_match.group(1)
    return value, unit


def http_post(url, token, payload, timeout=10):
    endpoint = url.rstrip("/") + "/@@instrument_acquisition_api_ingest"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib_request.Request(endpoint, data=body, headers={
        "Content-Type": "application/json",
        "X-Instrument-Token": token,
    })
    try:
        response = urllib_request.urlopen(request, timeout=timeout)
        raw = response.read()
        if sys.version_info[0] >= 3:
            raw = raw.decode("utf-8", "ignore")
        return response.getcode(), raw
    except urllib_error.HTTPError as exc:
        raw = exc.read()
        if sys.version_info[0] >= 3:
            raw = raw.decode("utf-8", "ignore")
        return exc.code, raw
    except Exception as exc:
        return None, str(exc)


def push_reading(raw_line):
    """把一条读数推给 LIMS 入站接口"""
    with LOCK:
        session_id = STATE["session_id"]
        instrument_code = STATE["instrument_code"]
    if not session_id:
        return
    value, unit = parse_reading(raw_line)
    payload = {
        "event_id": "relay-%s" % uuid.uuid4().hex,
        "session_id": session_id,
        "instrument_code": instrument_code,
        "received_at": now_iso(),
        "raw_text": raw_line,
        "parsed": {"value": value, "unit": unit, "stable": True},
    }
    code, body = http_post(CONFIG["lims_url"], CONFIG["token"], payload)
    if code in (200, 201, 202, 204):
        log("已推送: raw=%r value=%s unit=%s" % (raw_line, value or "-", unit or "-"))
    else:
        log("推送失败 code=%s body=%s" % (code, body))


# ----------------------------------------------------------------------
# 仪器连接线程
# ----------------------------------------------------------------------
def reader_loop():
    """持续连接仪器并收数据，直到会话停止"""
    while True:
        with LOCK:
            if not STATE["active"]:
                return
            host = STATE["instrument_host"]
            port = STATE["instrument_port"]
            session_id = STATE["session_id"]

        sock = None
        try:
            sock = socket.create_connection(
                (host, port), timeout=CONFIG["connect_timeout"])
            with LOCK:
                if not STATE["active"] or STATE["session_id"] != session_id:
                    return
                STATE["connected"] = True
                STATE["last_message"] = u"仪器已连接 %s:%s" % (host, port)
            log("仪器已连接 %s:%s" % (host, port))

            buf = ""
            while True:
                data = sock.recv(4096)
                if not data:
                    break
                with LOCK:
                    if not STATE["active"] or STATE["session_id"] != session_id:
                        return
                buf += data.decode("utf-8", "ignore")
                lines = buf.split("\n")
                buf = lines.pop()
                for line in lines:
                    line = line.strip().strip("\r")
                    if line:
                        push_reading(line)
        except Exception as exc:
            log("仪器连接错误: %s" % exc)
        finally:
            if sock:
                try:
                    sock.close()
                except Exception:
                    pass
            with LOCK:
                if STATE["session_id"] == session_id:
                    STATE["connected"] = False
                    STATE["last_message"] = u"仪器连接断开，等待重连"

        with LOCK:
            if not STATE["active"] or STATE["session_id"] != session_id:
                return
        time.sleep(CONFIG["reconnect_delay"])


# ----------------------------------------------------------------------
# HTTP 接口
# ----------------------------------------------------------------------
def read_body(handler):
    length = int(handler.headers.get("Content-Length", 0) or 0)
    if length <= 0:
        return {}
    raw = handler.rfile.read(length)
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {}


def send_json(handler, status, data):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def status_payload():
    with LOCK:
        return {
            "success": True,
            "active": STATE["active"],
            "session_id": STATE["session_id"],
            "operator": STATE["operator"],
            "instrument_code": STATE["instrument_code"],
            "instrument_host": STATE["instrument_host"],
            "instrument_port": STATE["instrument_port"],
            "instrument_connected": STATE["connected"],
            "last_message": STATE["last_message"],
        }


def handle_status(handler):
    send_json(handler, 200, status_payload())


def handle_start(handler):
    body = read_body(handler)
    session_id = (body.get("session_id") or u"").strip()
    instrument_code = (body.get("instrument_code") or u"").strip()
    host = (body.get("host") or u"").strip()
    operator = (body.get("operator") or u"").strip()
    force = bool(body.get("force"))
    try:
        port = int(body.get("port") or 0)
    except (TypeError, ValueError):
        port = 0

    if not session_id or not host or not port:
        send_json(handler, 400, {
            "success": False,
            "message": u"缺少 session_id / host / port",
        })
        return

    with LOCK:
        if STATE["active"]:
            if STATE["session_id"] == session_id:
                # 幂等：同一会话重复开始
                send_json(handler, 200, {
                    "success": True,
                    "message": u"已开始",
                    "instrument_connected": STATE["connected"],
                })
                return
            if not force:
                # 互斥：仪器正被其他会话占用（由 LIMS 端弹确认框决定是否挤掉）
                send_json(handler, 409, {
                    "success": False,
                    "message": u"用户 %s 正在使用该仪器（会话 %s）"
                               % (STATE["operator"] or u"未知",
                                  STATE["session_id"]),
                    "occupied_by": STATE["session_id"],
                    "operator": STATE["operator"],
                })
                return
            # force：挤掉旧会话，释放仪器后绑定新会话
            log("会话 %s（用户 %s）被新会话 %s 挤掉"
                % (STATE["session_id"], STATE["operator"] or u"未知",
                   session_id))
            STATE["active"] = False
            STATE["connected"] = False

        # 新会话：先登记，再连接
        STATE.update({
            "active": True,
            "session_id": session_id,
            "instrument_code": instrument_code,
            "instrument_host": host,
            "instrument_port": port,
            "operator": operator,
            "connected": False,
            "last_message": u"",
        })

    # 同步连接仪器，拿到结果再返回给 LIMS
    sock = None
    try:
        sock = socket.create_connection(
            (host, port), timeout=CONFIG["connect_timeout"])
    except Exception as exc:
        with LOCK:
            STATE["active"] = False
            STATE["connected"] = False
            STATE["last_message"] = u"连接仪器失败: %s" % exc
        send_json(handler, 502, {
            "success": False,
            "message": u"连接仪器 %s:%s 失败：%s" % (host, port, exc),
        })
        return
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass

    # 连接成功，交给后台线程持续收数据
    with LOCK:
        STATE["connected"] = True
        STATE["last_message"] = u"仪器已连接 %s:%s" % (host, port)
    # Python 2.7 的 threading.Thread 不支持 daemon 关键字参数，用 setDaemon
    _thread = threading.Thread(target=reader_loop)
    _thread.setDaemon(True)
    _thread.start()
    log("开始采集：session=%s instrument=%s %s:%s"
        % (session_id, instrument_code, host, port))
    send_json(handler, 200, {
        "success": True,
        "message": u"仪器已连接 %s:%s" % (host, port),
        "instrument_connected": True,
    })


def handle_stop(handler):
    body = read_body(handler)
    session_id = (body.get("session_id") or u"").strip()
    with LOCK:
        if STATE["active"] and (not session_id or STATE["session_id"] == session_id):
            STATE["active"] = False
            STATE["connected"] = False
            STATE["last_message"] = u"已停止采集"
            log("停止采集：session=%s" % session_id)
    send_json(handler, 200, {
        "success": True,
        "message": u"已停止采集",
    })


class RelayHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.rstrip("/") in ("", "/status"):
            handle_status(self)
        else:
            send_json(self, 404, {"success": False, "message": "not found"})

    def do_POST(self):
        path = self.path.rstrip("/")
        if path == "/start":
            handle_start(self)
        elif path == "/stop":
            handle_stop(self)
        else:
            send_json(self, 404, {"success": False, "message": "not found"})

    def log_message(self, *args):
        pass  # 关闭默认访问日志


def main():
    parser = argparse.ArgumentParser(description="仪器采集中转站服务")
    parser.add_argument("--listen-host", default=DEFAULTS["listen_host"])
    parser.add_argument("--listen-port", type=int, default=DEFAULTS["listen_port"])
    parser.add_argument("--lims-url", default=DEFAULTS["lims_url"])
    parser.add_argument("--token", default=DEFAULTS["token"])
    parser.add_argument("--connect-timeout", type=int,
                        default=DEFAULTS["connect_timeout"])
    parser.add_argument("--reconnect-delay", type=int,
                        default=DEFAULTS["reconnect_delay"])
    args = parser.parse_args()

    CONFIG["lims_url"] = args.lims_url
    CONFIG["token"] = args.token
    CONFIG["connect_timeout"] = args.connect_timeout
    CONFIG["reconnect_delay"] = args.reconnect_delay

    server = HTTPServer((args.listen_host, args.listen_port), RelayHandler)
    print("=" * 60)
    print("仪器采集中转站服务已启动")
    print("  监听:  http://%s:%d" % (args.listen_host, args.listen_port))
    print("  LIMS:  %s" % args.lims_url)
    print("  接口:  GET /status | POST /start | POST /stop")
    print("=" * 60)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已退出")


if __name__ == "__main__":
    main()
