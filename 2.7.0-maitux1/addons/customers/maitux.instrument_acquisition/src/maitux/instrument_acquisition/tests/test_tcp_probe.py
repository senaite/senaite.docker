# -*- coding: utf-8 -*-
"""TCP 连通性探测测试（纯 socket 逻辑，不依赖 Zope）

直接按文件路径加载 tcp_probe.py（避免触发包级 __init__ 的 Zope 依赖）。
"""

import os
import socket
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_MODULE_PATH = os.path.join(_HERE, "..", "services", "tcp_probe.py")


def _load_source(name, path):
    """按文件路径加载模块（py2 用 imp；py3.12+ 用 importlib.util）"""
    try:
        import imp
        return imp.load_source(name, path)
    except ImportError:
        import importlib.util
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


_probe = _load_source("maitux_tcp_probe_test", _MODULE_PATH)


def _free_port():
    """返回一个当前未监听的本地端口"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class TcpProbeTest(unittest.TestCase):
    """校验 probe_tcp 的连通性判定"""

    def test_empty_host(self):
        ok, message = _probe.probe_tcp("", "8080")
        self.assertFalse(ok)
        self.assertIn(u"未配置", message)

    def test_invalid_port(self):
        ok, message = _probe.probe_tcp("127.0.0.1", "abc")
        self.assertFalse(ok)
        ok, message = _probe.probe_tcp("127.0.0.1", "99999")
        self.assertFalse(ok)
        self.assertIn(u"端口", message)

    def test_connect_success(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        try:
            port = server.getsockname()[1]
            ok, message = _probe.probe_tcp("127.0.0.1", port, timeout=2)
            self.assertTrue(ok, message)
            self.assertIn(u"TCP 连接成功", message)
        finally:
            server.close()

    def test_connect_failure(self):
        port = _free_port()
        ok, message = _probe.probe_tcp("127.0.0.1", port, timeout=1)
        self.assertFalse(ok)
        # Windows 上对未监听端口可能立即拒绝，也可能超时
        self.assertTrue(u"无法连接" in message or u"超时" in message, message)

    def test_default_timeout_constant(self):
        # 默认超时来自 phase1_targets 常量（try 导入失败时为 3）
        self.assertGreaterEqual(_probe.PHASE1_TCP_PROBE_TIMEOUT, 1)


if __name__ == "__main__":
    unittest.main()
