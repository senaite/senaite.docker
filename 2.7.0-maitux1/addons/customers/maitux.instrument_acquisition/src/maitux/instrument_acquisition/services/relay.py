# -*- coding: utf-8 -*-
"""进程内仪器连接服务（多仪器并行版，集成进 SENAITE LIMS）

场景：云上 LIMS 被多个实验室共用，各实验室操作本地的仪器并查看本地数据，
多地可能同时各自采集。因此本服务按"仪器"（host:port）管理多条连接：

- 每台仪器一个独立连接（TCP Client）+ 独立 reader 线程 + 独立内存队列
- 互斥/挤占按仪器粒度：同一台仪器同一时间只允许一个会话占用
- 读数进对应仪器的队列，由采集页轮询（请求线程）批量写入会话
- 仪器地址（含内网穿透后的公网地址）由 LIMS 从解析模板读取后传入

设计要点：
- reader 线程只做 socket 收发，不访问 ZODB；数据写入都在请求线程完成
- Windows/py2 下跨线程 close 不会向对端发 FIN，连接必须由持有它的
  reader 线程自行关闭（recv 超时周期内检测会话结束并关闭）
- 进程内状态随 LIMS 重启自然重置（连接断开，仪器释放）
"""

import logging
import re
import socket
import threading
import time
from datetime import datetime

try:
    import queue as Queue
except ImportError:  # Python 2
    import Queue

logger = logging.getLogger("maitux.instrument_acquisition")

# 连接参数
CONFIG = {
    "connect_timeout": 3,       # 开始采集时连接仪器的超时（秒）
    "reconnect_delay": 3,       # 断线后重连间隔（秒）
    "recv_timeout": 1.0,        # 收数据 socket 的接收超时（秒）
}

# 单条读数队列上限
_QUEUE_MAX = 1000

# 连接锁与连接表：{instrument_key: _Connection}
LOCK = threading.Lock()
CONNECTIONS = {}


def _instrument_key(host, port):
    """仪器唯一键（互斥粒度）"""
    return u"{}:{}".format((host or u"").strip(), int(port))


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


class _Connection(object):
    """一台仪器的采集连接"""

    def __init__(self, instrument_key, session_id, instrument_code,
                 host, port, operator):
        self.instrument_key = instrument_key
        self.session_id = session_id
        self.instrument_code = instrument_code
        self.host = host
        self.port = int(port)
        self.operator = operator or u""
        self.active = True          # 会话是否有效（stop/挤掉后 False）
        self.connected = False      # 当前是否已连上仪器
        self.last_message = u""
        self.sock = None            # 当前连接（由 reader 线程持有并关闭）
        self.queue = Queue.Queue()  # 本仪器读数队列
        self.thread = None

    def to_dict(self):
        return {
            "active": self.active,
            "session_id": self.session_id,
            "instrument_code": self.instrument_code,
            "host": self.host,
            "port": self.port,
            "operator": self.operator,
            "connected": self.connected,
            "last_message": self.last_message,
        }


def get_status():
    """返回所有仪器连接的当前状态列表"""
    with LOCK:
        return [conn.to_dict() for conn in CONNECTIONS.values()]


def status_for(host, port):
    """按仪器地址查询状态；无连接返回 None"""
    key = _instrument_key(host, port)
    with LOCK:
        conn = CONNECTIONS.get(key)
        return conn.to_dict() if conn else None


def is_active(session_id):
    """该会话是否仍占用着某台仪器（被挤掉/停止后返回 False）"""
    with LOCK:
        return any(conn.active and conn.session_id == session_id
                   for conn in CONNECTIONS.values())


def start(session_id, instrument_code, host, port,
          operator=u"", force=False):
    """开始采集：按仪器互斥/挤占检查，连接仪器并起后台收数据线程

    :param session_id: LIMS 采集会话 id
    :param instrument_code: 仪器标识
    :param host: 仪器 TCP 地址（可为本机/内网/穿透后的公网地址）
    :param port: 仪器 TCP 端口
    :param operator: 当前操作用户（显示名），记录占用者
    :param force: True 时挤掉该仪器的当前占用者（LIMS 端已弹确认框）
    :returns: (success, message)
    """
    key = _instrument_key(host, port)
    with LOCK:
        existing = CONNECTIONS.get(key)
        if existing is not None:
            if existing.session_id == session_id:
                return True, u"已开始"
            if not force:
                return False, (u"用户 %s 正在使用该仪器（会话 %s）"
                               % (existing.operator or u"未知",
                                  existing.session_id))
            # force：挤掉该仪器的旧会话
            logger.info("Relay: session %s (user %s) preempted by %s",
                        existing.session_id, existing.operator or u"unknown",
                        session_id)
            existing.active = False
            existing.connected = False
            CONNECTIONS.pop(key, None)

        conn = _Connection(key, session_id, instrument_code, host, port,
                           operator)
        CONNECTIONS[key] = conn

    # 同步连接仪器（锁外执行，避免长时间持锁）
    sock = None
    try:
        sock = socket.create_connection(
            (host, int(port)), timeout=CONFIG["connect_timeout"])
    except Exception as exc:
        with LOCK:
            CONNECTIONS.pop(key, None)
        logger.warning("Relay: connect %s:%s failed: %s", host, port, exc)
        return False, u"连接仪器 %s:%s 失败：%s" % (host, port, exc)

    sock.settimeout(CONFIG["recv_timeout"])
    with LOCK:
        current = CONNECTIONS.get(key)
        if current is None or current.session_id != session_id:
            try:
                sock.close()
            except Exception:
                pass
            return False, u"会话已变更，请重试"
        current.sock = sock
        current.connected = True
        current.last_message = u"仪器已连接 %s:%s" % (host, port)

    # Python 2.7 的 threading.Thread 不支持 daemon 关键字参数，用 setDaemon
    _thread = threading.Thread(target=_reader_loop, args=(current,))
    _thread.setDaemon(True)
    _thread.start()
    current.thread = _thread
    logger.info("Relay: started session=%s instrument=%s %s:%s operator=%s",
                session_id, instrument_code, host, port, operator)
    return True, u"仪器已连接 %s:%s" % (host, port)


def stop(session_id):
    """停止采集：释放该会话占用的仪器。

    连接由 reader 线程在接收超时周期内自行关闭（Windows/py2 下必须由
    持有 socket 的线程关闭，跨线程 close 不会向对端发 FIN）。
    """
    with LOCK:
        for key, conn in CONNECTIONS.items():
            if conn.session_id == session_id:
                conn.active = False
                conn.connected = False
                conn.last_message = u"已停止采集"
                CONNECTIONS.pop(key, None)
                logger.info("Relay: stopped session=%s", session_id)
                return True
    return False


def drain_queue(session_id):
    """取出指定会话对应仪器缓冲的读数（请求线程调用）

    :returns: [{session_id, raw_text, value, unit, received_at}, ...]
    """
    with LOCK:
        conn = None
        for candidate in CONNECTIONS.values():
            if candidate.session_id == session_id:
                conn = candidate
                break
    if conn is None:
        return []
    items = []
    while True:
        try:
            items.append(conn.queue.get_nowait())
        except Queue.Empty:
            break
    return items


def pop_queue_item(session_id):
    """从指定会话的仪器队列取出一条读数（不消费时返回 None）

    供 flush 逐条处理：处理失败时可 requeue 重试，避免一次性取走全部后
    写入失败导致数据丢失。
    """
    with LOCK:
        conn = None
        for candidate in CONNECTIONS.values():
            if candidate.session_id == session_id:
                conn = candidate
                break
    if conn is None:
        return None
    try:
        return conn.queue.get_nowait()
    except Queue.Empty:
        return None


def requeue(session_id, item):
    """把处理失败/需重试的读数放回该会话的仪器队列队尾

    会话已不存在（被挤掉/停止）时丢弃并记录日志。
    """
    with LOCK:
        conn = None
        for candidate in CONNECTIONS.values():
            if candidate.session_id == session_id:
                conn = candidate
                break
    if conn is None:
        logger.warning(
            "Relay: requeue target session gone, dropped reading: %r",
            item.get("raw_text", u""))
        return False
    item["retries"] = item.get("retries", 0) + 1
    try:
        conn.queue.put_nowait(item)
        return True
    except Queue.Full:
        logger.warning("Relay: requeue queue full, dropped reading: %r",
                       item.get("raw_text", u""))
        return False


def _push_reading(conn, raw_line):
    """reader 线程把一行读数放入该仪器的队列"""
    value, unit = parse_reading(raw_line)
    item = {
        "session_id": conn.session_id,
        "raw_text": raw_line,
        "value": value,
        "unit": unit,
        "received_at": datetime.now().isoformat(),
    }
    try:
        conn.queue.put_nowait(item)
    except Queue.Full:
        try:
            conn.queue.get_nowait()  # 队列满时丢弃最旧一条
        except Queue.Empty:
            pass
        try:
            conn.queue.put_nowait(item)
        except Queue.Full:
            logger.warning("Relay: reading queue full for %s, dropped",
                           conn.instrument_key)


def _reader_loop(conn):
    """后台收数据线程：连接仪器并按行读取（不访问数据库）。

    连接由本线程持有并关闭；recv 超时周期性检查会话是否结束（stop/挤掉）。
    """
    try:
        while conn.active:
            sock = conn.sock
            if sock is None:
                # 断线重连
                try:
                    sock = socket.create_connection(
                        (conn.host, conn.port),
                        timeout=CONFIG["connect_timeout"])
                    sock.settimeout(CONFIG["recv_timeout"])
                    with LOCK:
                        if not conn.active:
                            try:
                                sock.close()
                            except Exception:
                                pass
                            return
                        conn.sock = sock
                        conn.connected = True
                        conn.last_message = u"仪器已连接 %s:%s" % (
                            conn.host, conn.port)
                except Exception as exc:
                    logger.warning("Relay: reconnect failed for %s: %s",
                                   conn.instrument_key, exc)
                    time.sleep(CONFIG["reconnect_delay"])
                    continue

            # 收数据
            buf = ""
            try:
                while conn.active:
                    try:
                        data = sock.recv(4096)
                    except socket.timeout:
                        continue  # 超时：回到 while 检查 conn.active
                    except Exception:
                        break
                    if not data:
                        break
                    buf += data.decode("utf-8", "ignore")
                    lines = buf.split("\n")
                    buf = lines.pop()
                    for line in lines:
                        line = line.strip().strip("\r")
                        if line:
                            _push_reading(conn, line)
            except Exception:
                pass

            # 断开
            with LOCK:
                if conn.active:
                    conn.connected = False
                    conn.last_message = u"仪器连接断开，等待重连"
                    conn.sock = None
            try:
                sock.close()
            except Exception:
                pass
            if conn.active:
                time.sleep(CONFIG["reconnect_delay"])
    finally:
        # 会话结束：确保连接被本线程关闭
        with LOCK:
            sock = conn.sock
            conn.sock = None
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
