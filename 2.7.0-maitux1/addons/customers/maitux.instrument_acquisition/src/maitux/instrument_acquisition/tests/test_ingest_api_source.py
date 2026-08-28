# -*- coding: utf-8 -*-
"""入站接口源码级约束测试

第一阶段先做源码级/轻量级约束测试：
确认 endpoint 名称、固定 token 校验、event_id 幂等逻辑存在。
不启动 Zope。
"""

import io
import os
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKG_ROOT = os.path.join(_HERE, "..")
_API_VIEWS = os.path.join(_PKG_ROOT, "api", "views.py")
_API_ZCML = os.path.join(_PKG_ROOT, "api", "configure.zcml")


def _read(path):
    # 显式 utf-8：Windows 默认编码（GBK）读 UTF-8 源文件会失败
    with io.open(path, "r", encoding="utf-8") as handle:
        return handle.read()


class IngestApiSourceTest(unittest.TestCase):
    """校验入站接口的源码级约束"""

    @classmethod
    def setUpClass(cls):
        cls.views_source = _read(_API_VIEWS)
        cls.zcml_source = _read(_API_ZCML)

    def test_endpoint_registered(self):
        self.assertIn("instrument_acquisition_api_ingest", self.zcml_source)
        self.assertIn("IngestReadingAPI", self.zcml_source)

    def test_token_validation_present(self):
        self.assertIn("X-Instrument-Token", self.views_source)
        self.assertIn("PHASE1_INGEST_TOKEN", self.views_source)
        self.assertIn("Invalid token", self.views_source)

    def test_event_id_dedup_logic_present(self):
        # 幂等去重由 session_store.ingest_event 承担
        self.assertIn("ingest_event", self.views_source)
        self.assertIn("duplicate", self.views_source)

    def test_session_lookup_present(self):
        self.assertIn("resolve_worksheet_by_session_id", self.views_source)
        self.assertIn("No active session found", self.views_source)

    def test_method_restriction(self):
        self.assertIn("Method not allowed", self.views_source)
        self.assertIn('self.request.method != "POST"', self.views_source)

    def test_listening_guard_referenced(self):
        # 未「开始采集」的会话（listening=False）推送应被拒绝
        self.assertIn("listening", self.views_source)

    def test_rejected_statuses(self):
        self.assertIn('"status": "rejected"', self.views_source)
        self.assertIn('"status": "created"', self.views_source)

    def test_agent_config_endpoint_registered(self):
        # 远端采集端（agent）联动配置接口已注册
        self.assertIn("instrument_acquisition_api_agent_config",
                      self.zcml_source)
        self.assertIn("AgentConfigAPI", self.views_source)

    def test_agent_config_returns_start_and_address(self):
        self.assertIn("resolve_listening_worksheet_by_instrument",
                      self.views_source)
        self.assertIn('"start": True', self.views_source)
        self.assertIn('"start": False', self.views_source)
        self.assertIn("get_instrument_tcp_address", self.views_source)

    def test_ingest_supports_sessionless_push(self):
        # agent 无状态：不带 session_id 推送，按 instrument_code 归会话
        self.assertIn("Missing session_id or instrument_code",
                      self.views_source)
        self.assertIn("No active listening session for", self.views_source)

    def test_token_verification_via_template(self):
        # 一个中转站一个 Token：按仪器模板登记的 agent_token 校验
        self.assertIn("_verify_token", self.views_source)
        self.assertIn("agent_token", self.views_source)
        self.assertIn("_get_template_for_instrument", self.views_source)
        # 固定共享 Token 兼容保留
        self.assertIn("PHASE1_INGEST_TOKEN", self.views_source)

    def test_agent_api_url_field_returned(self):
        # 采集端接口地址（与天平地址分离）随 agent_config 返回
        self.assertIn("agent_api_url", self.views_source)


if __name__ == "__main__":
    unittest.main()
