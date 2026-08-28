# -*- coding: utf-8 -*-
"""第一阶段会话存储测试（event_id 去重、会话创建、分配与撤销）

需要 Zope 环境（zope.annotation、bika.lims.api 可导入）才能运行；
在纯 Python 环境下自动跳过。

通过 fake 对象 + monkeypatch 覆盖 session_store 依赖的 api 辅助函数，
验证 annotations 中的会话、读数、分配、日志逻辑。
"""

import unittest

try:
    from zope.annotation.attribute import AttributeAnnotatable

    from bika.lims import api as bika_api

    from maitux.instrument_acquisition.services import session_store
    from maitux.instrument_acquisition.services import phase1_targets
    from maitux.instrument_acquisition.services.phase1_targets import (
        T_WEIGHT_KEYWORD,
        make_target_key,
    )

    class FakePortal(AttributeAnnotatable):
        """替代 portal 的 annotations 容器"""

    class FakeInstrument(AttributeAnnotatable):
        def __init__(self, uid, code, title):
            self._uid = uid
            self.code = code
            self.title = title

        def UID(self):
            return self._uid

    class FakeWorksheet(AttributeAnnotatable):
        def __init__(self, uid, instrument, analyses=None):
            self._uid = uid
            self._instrument = instrument
            self._analyses = analyses or []
            self.id = uid

        def UID(self):
            return self._uid

        def getInstrument(self):
            return self._instrument

        def getAnalyses(self):
            return self._analyses

    _IMPORT_OK = True
except Exception:  # pragma: no cover
    _IMPORT_OK = False

    class FakePortal(object):
        pass

    class FakeInstrument(object):
        pass

    class FakeWorksheet(object):
        pass


@unittest.skipUnless(_IMPORT_OK, "Zope 环境不可用，跳过会话存储测试")
class SessionStoreTest(unittest.TestCase):

    def setUp(self):
        # 覆盖 api 辅助函数，让 fake 对象可被 store 使用
        self._orig = {}
        self._patch("get_uid", lambda obj: obj.UID())
        self._patch("get_id", lambda obj: getattr(
            obj, "code", getattr(obj, "id", obj.UID())))
        self._patch("get_title", lambda obj: getattr(
            obj, "title", getattr(obj, "code", obj.UID())))
        self._patch("get_path", lambda obj: obj.UID())
        self._patch("is_object", lambda obj: True)
        # portal 反查：直接返回 FakePortal（替代 api.get_portal）
        self._orig_portal = session_store._get_portal
        self.portal = FakePortal()
        session_store._get_portal = lambda context: self.portal

        # 中转站调用打桩：默认连接成功（真实 HTTP 连接在集成测试验证）
        self._orig_start_instrument = session_store.start_instrument
        self._orig_stop_instrument = session_store.stop_instrument
        self.start_calls = []
        session_store.start_instrument = self._fake_start_instrument
        session_store.stop_instrument = lambda sid: (True, u"已停止")

        # relay 占用归属打桩：默认视为会话仍占用仪器（真实连接在集成测试验证）
        self._orig_relay_is_active = session_store.relay.is_active
        session_store.relay.is_active = lambda sid: True
        # 清理 relay 连接表，避免测试间互相污染
        session_store.relay.CONNECTIONS.clear()
        self._orig_ingest_event = session_store.ingest_event

        # 默认走进程内 relay 路径（现有测试语义）；agent 模式单独测试
        self._orig_agent_mode = phase1_targets.PHASE1_AGENT_MODE
        phase1_targets.PHASE1_AGENT_MODE = False

        self.instrument = FakeInstrument("inst-1", "BALANCE-01", u"电子天平")
        self.worksheet = FakeWorksheet("ws-1", self.instrument)
        self.worksheet2 = FakeWorksheet("ws-2", self.instrument)
        self.instrument2 = FakeInstrument("inst-2", "BALANCE-02", u"电子天平2")
        self.worksheet_other = FakeWorksheet("ws-3", self.instrument2)

    def tearDown(self):
        session_store._get_portal = self._orig_portal
        session_store.start_instrument = self._orig_start_instrument
        session_store.stop_instrument = self._orig_stop_instrument
        session_store.relay.is_active = self._orig_relay_is_active
        session_store.relay.CONNECTIONS.clear()
        session_store.ingest_event = self._orig_ingest_event
        phase1_targets.PHASE1_AGENT_MODE = self._orig_agent_mode
        for name, original in self._orig.items():
            if original is None:
                delattr(bika_api, name)
            else:
                setattr(bika_api, name, original)

    def _patch(self, name, func):
        self._orig[name] = getattr(bika_api, name, None)
        setattr(bika_api, name, func)

    def _fake_start_instrument(self, worksheet, session_id, instrument_code,
                               force=False, operator=u""):
        self.start_calls.append({
            "session_id": session_id,
            "force": force,
            "operator": operator,
        })
        return True, u"仪器已连接"

    def _start_session(self, worksheet):
        session, created = session_store.ensure_session(worksheet)
        self.assertTrue(created)
        return session

    def _ingest(self, worksheet, session, event_id="e-1",
                raw="ST,GS,0.9678,mg", value="0.9678"):
        # 只有「开始采集」（listening）后才能入库
        session_store.start_listening(worksheet)
        return session_store.ingest_event(
            worksheet, event_id, session["session_id"],
            session["instrument_code"], raw,
            parsed_value=value, unit="mg")

    # ------------------------------------------------------------------

    def test_session_created_and_recovered(self):
        session, created = session_store.ensure_session(self.worksheet)
        self.assertTrue(created)
        self.assertEqual(session["status"], session_store.SESSION_ACTIVE)
        # 默认未开始采集
        self.assertFalse(session_store.is_listening(self.worksheet))

        session2, created2 = session_store.ensure_session(self.worksheet)
        self.assertFalse(created2)
        self.assertEqual(session2["session_id"], session["session_id"])

    def test_session_requires_instrument(self):
        empty = FakeWorksheet("ws-empty", None)
        with self.assertRaises(ValueError):
            session_store.ensure_session(empty)

    def test_listening_switch(self):
        session = self._start_session(self.worksheet)
        self.assertFalse(session_store.is_listening(self.worksheet))

        ok, message = session_store.start_listening(self.worksheet)
        self.assertTrue(ok)
        self.assertTrue(session_store.is_listening(self.worksheet))
        # 幂等
        ok, message = session_store.start_listening(self.worksheet)
        self.assertTrue(ok)

        ok, message = session_store.stop_listening(self.worksheet)
        self.assertTrue(ok)
        self.assertFalse(session_store.is_listening(self.worksheet))
        # 幂等
        ok, message = session_store.stop_listening(self.worksheet)
        self.assertTrue(ok)

    def test_is_listening_invalidated_when_preempted(self):
        session = self._start_session(self.worksheet)
        session_store.start_listening(self.worksheet)
        self.assertTrue(session_store.is_listening(self.worksheet))
        # 模拟被其他用户挤掉（relay 中该会话不再占用仪器）
        session_store.relay.is_active = lambda sid: False
        self.assertFalse(session_store.is_listening(self.worksheet))

    def test_start_listening_passes_force_and_operator(self):
        session = self._start_session(self.worksheet)
        ok, message = session_store.start_listening(
            self.worksheet, force=True)
        self.assertTrue(ok)
        self.assertEqual(len(self.start_calls), 1)
        self.assertTrue(self.start_calls[0]["force"])
        # 记录占用者
        data = session_store.get_session_data(self.worksheet)
        self.assertTrue(data["active_session"].get("occupied_by"))

    def test_start_listening_default_no_force(self):
        session = self._start_session(self.worksheet)
        ok, message = session_store.start_listening(self.worksheet)
        self.assertTrue(ok)
        self.assertFalse(self.start_calls[0]["force"])

    def test_stop_listening_clears_occupier(self):
        session = self._start_session(self.worksheet)
        session_store.start_listening(self.worksheet)
        data = session_store.get_session_data(self.worksheet)
        self.assertTrue(data["active_session"].get("occupied_by"))
        session_store.stop_listening(self.worksheet)
        data = session_store.get_session_data(self.worksheet)
        self.assertEqual(data["active_session"].get("occupied_by"), u"")

    def test_ingest_rejected_when_not_listening(self):
        session = self._start_session(self.worksheet)
        # 未点「开始采集」时推送被拒
        status, event = session_store.ingest_event(
            self.worksheet, "e-1", session["session_id"],
            session["instrument_code"], "ST,GS,0.9678,mg")
        self.assertEqual(status, "rejected")

        # 开始采集后可入库
        session_store.start_listening(self.worksheet)
        status, event = session_store.ingest_event(
            self.worksheet, "e-1", session["session_id"],
            session["instrument_code"], "ST,GS,0.9678,mg")
        self.assertEqual(status, "created")

        # 停止采集后再次被拒
        session_store.stop_listening(self.worksheet)
        status, event = session_store.ingest_event(
            self.worksheet, "e-2", session["session_id"],
            session["instrument_code"], "ST,GS,1.2345,mg")
        self.assertEqual(status, "rejected")

    def test_ensure_session_does_not_close_other_worksheet(self):
        session1 = self._start_session(self.worksheet)
        # 同一仪器在另一个 Worksheet 开启会话，不再强关第一个会话
        # （仪器占用互斥由中转站在「开始采集」时负责）
        session2, created2 = session_store.ensure_session(self.worksheet2)
        self.assertTrue(created2)
        self.assertNotEqual(session1["session_id"], session2["session_id"])
        self.assertIsNotNone(session_store.get_active_session(self.worksheet))
        self.assertIsNotNone(session_store.get_active_session(self.worksheet2))

    def test_start_listening_rejected_when_relay_busy(self):
        session = self._start_session(self.worksheet)
        # 模拟中转站返回"仪器被占用"
        session_store.start_instrument = (
            lambda ws, sid, code, force=False, operator=u"":
            (False, u"用户 张三 正在使用该仪器（会话 sess-other）"))
        ok, message = session_store.start_listening(self.worksheet)
        self.assertFalse(ok)
        self.assertIn(u"正在使用", message)
        self.assertIn(u"张三", message)
        self.assertFalse(session_store.is_listening(self.worksheet))

    def test_start_listening_rejected_when_relay_unreachable(self):
        session = self._start_session(self.worksheet)
        session_store.start_instrument = (
            lambda ws, sid, code, force=False, operator=u"":
            (False, u"连接仪器失败：超时"))
        ok, message = session_store.start_listening(self.worksheet)
        self.assertFalse(ok)
        self.assertFalse(session_store.is_listening(self.worksheet))

    def test_session_recreated_when_instrument_changed(self):
        session1 = self._start_session(self.worksheet)
        self.assertEqual(session1["instrument_uid"], "inst-1")

        # 在 Worksheets 界面更换仪器后再次进入采集
        self.worksheet._instrument = self.instrument2
        session2, created2 = session_store.ensure_session(self.worksheet)
        self.assertTrue(created2)
        self.assertNotEqual(session2["session_id"], session1["session_id"])
        self.assertEqual(session2["instrument_uid"], "inst-2")
        self.assertEqual(session2["instrument_code"], "BALANCE-02")
        # 旧会话已关闭
        data = session_store.get_session_data(self.worksheet)
        self.assertEqual(data["active_session"]["status"],
                         session_store.SESSION_ACTIVE)
        self.assertEqual(data["active_session"]["instrument_uid"], "inst-2")

    def test_page_data_isolates_old_session_readings(self):
        session1 = self._start_session(self.worksheet)
        session_store.start_listening(self.worksheet)
        session_store.ingest_event(
            self.worksheet, "e-old", session1["session_id"],
            "BALANCE-01", "ST,GS,0.9678,mg", parsed_value="0.9678")

        # 更换仪器重建会话后，旧读数不混入新会话列表
        self.worksheet._instrument = self.instrument2
        session2, created2 = session_store.ensure_session(self.worksheet)
        self.assertTrue(created2)

        page = session_store.get_page_data(self.worksheet)
        self.assertEqual(page["counts"]["total"], 0)
        self.assertEqual(len(page["readings"]), 0)
        # 旧读数仍保留在 annotations 中（审计不删除）
        data = session_store.get_session_data(self.worksheet)
        self.assertIn("e-old", data["events"])

        # 新会话可正常接收新读数
        session_store.start_listening(self.worksheet)
        status, event = session_store.ingest_event(
            self.worksheet, "e-new", session2["session_id"],
            "BALANCE-02", "ST,GS,1.2345,mg", parsed_value="1.2345")
        self.assertEqual(status, "created")
        page = session_store.get_page_data(self.worksheet)
        self.assertEqual(page["counts"]["total"], 1)

    def test_ingest_created_and_deduplicated(self):
        session = self._start_session(self.worksheet)
        status, event = self._ingest(self.worksheet, session)
        self.assertEqual(status, "created")
        self.assertEqual(event["status"], session_store.STATUS_PENDING)

        # 同一 event_id 重复推送 -> duplicate，不重复入库
        status2, event2 = self._ingest(self.worksheet, session)
        self.assertEqual(status2, "duplicate")
        data = session_store.get_session_data(self.worksheet)
        self.assertEqual(len(data["events"]), 1)

    def test_ingest_rejected_on_session_mismatch(self):
        session = self._start_session(self.worksheet)
        session_store.start_listening(self.worksheet)
        status, event = session_store.ingest_event(
            self.worksheet, "e-2", "wrong-session-id",
            session["instrument_code"], "x")
        self.assertEqual(status, "rejected")

        status, event = session_store.ingest_event(
            self.worksheet, "e-3", session["session_id"],
            "WRONG-INSTRUMENT", "x")
        self.assertEqual(status, "rejected")

    # ------------------------------------------------------------------
    # flush 失败重试
    # ------------------------------------------------------------------

    def _seed_relay_queue(self, session_id, retries=0):
        """往 relay 连接表塞一条带队列的连接，用于验证 flush 逻辑"""
        relay = session_store.relay
        conn = relay._Connection("127.0.0.1:9000", session_id, "BAL-01",
                                 "127.0.0.1", 9000, u"tester")
        relay.CONNECTIONS["127.0.0.1:9000"] = conn
        conn.queue.put_nowait({
            "session_id": session_id,
            "raw_text": u"ST,GS,0.9678,mg",
            "value": u"0.9678",
            "unit": u"mg",
            "received_at": u"2026-08-01T00:00:00",
            "retries": retries,
        })
        return conn

    def test_flush_retries_rejected_reading(self):
        session = self._start_session(self.worksheet)
        session_store.start_listening(self.worksheet)
        conn = self._seed_relay_queue(session["session_id"])

        # 写入被拒：读数应重新入队并计数重试，不丢失
        session_store.ingest_event = (
            lambda *a, **k: ("rejected", None))
        count = session_store.flush_relay_readings(self.worksheet)
        self.assertEqual(count, 0)
        self.assertEqual(conn.queue.qsize(), 1)
        item = conn.queue.get_nowait()
        self.assertEqual(item["retries"], 1)

    def test_flush_drops_after_max_retries(self):
        session = self._start_session(self.worksheet)
        session_store.start_listening(self.worksheet)
        conn = self._seed_relay_queue(
            session["session_id"],
            retries=session_store.RELAY_FLUSH_MAX_RETRIES)

        session_store.ingest_event = (
            lambda *a, **k: ("rejected", None))
        count = session_store.flush_relay_readings(self.worksheet)
        self.assertEqual(count, 0)
        # 超过重试上限：丢弃，不再堆积
        self.assertEqual(conn.queue.qsize(), 0)

    def test_flush_requeues_on_exception(self):
        session = self._start_session(self.worksheet)
        session_store.start_listening(self.worksheet)
        conn = self._seed_relay_queue(session["session_id"])

        def boom(*a, **k):
            raise RuntimeError("db down")
        session_store.ingest_event = boom
        count = session_store.flush_relay_readings(self.worksheet)
        self.assertEqual(count, 0)
        self.assertEqual(conn.queue.qsize(), 1)

    def test_flush_ingests_successfully(self):
        session = self._start_session(self.worksheet)
        session_store.start_listening(self.worksheet)
        conn = self._seed_relay_queue(session["session_id"])

        count = session_store.flush_relay_readings(self.worksheet)
        self.assertEqual(count, 1)
        self.assertEqual(conn.queue.qsize(), 0)

    def test_assign_and_multi_assign(self):
        session = self._start_session(self.worksheet)
        self._ingest(self.worksheet, session)

        tk1 = make_target_key("analysis-1", T_WEIGHT_KEYWORD)
        tk2 = make_target_key("analysis-2", T_WEIGHT_KEYWORD)

        ok, message = session_store.assign_reading(
            self.worksheet, "e-1", tk1)
        self.assertTrue(ok)
        # 一条读数分配给多个目标位（同源引用）
        ok, message = session_store.assign_reading(
            self.worksheet, "e-1", tk2)
        self.assertTrue(ok)

        data = session_store.get_session_data(self.worksheet)
        event = data["events"]["e-1"]
        self.assertEqual(event["status"], session_store.STATUS_ASSIGNED)
        self.assertIn(tk1, event["targets"])
        self.assertIn(tk2, event["targets"])
        self.assertEqual(len(data["assignments"]), 2)

    def test_assign_rejects_occupied_target(self):
        session = self._start_session(self.worksheet)
        self._ingest(self.worksheet, session, event_id="e-1")
        self._ingest(self.worksheet, session, event_id="e-2",
                     raw="ST,GS,1.2345,mg", value="1.2345")

        tk = make_target_key("analysis-1", T_WEIGHT_KEYWORD)
        self.assertTrue(session_store.assign_reading(
            self.worksheet, "e-1", tk)[0])
        ok, message = session_store.assign_reading(
            self.worksheet, "e-2", tk)
        self.assertFalse(ok)

    def test_unassign_returns_pending(self):
        session = self._start_session(self.worksheet)
        self._ingest(self.worksheet, session)

        tk = make_target_key("analysis-1", T_WEIGHT_KEYWORD)
        session_store.assign_reading(self.worksheet, "e-1", tk)

        ok, message = session_store.unassign_reading(self.worksheet, tk)
        self.assertTrue(ok)

        data = session_store.get_session_data(self.worksheet)
        event = data["events"]["e-1"]
        self.assertEqual(event["status"], session_store.STATUS_PENDING)
        self.assertEqual(event["targets"], [])
        self.assertNotIn(tk, data["assignments"])

    def test_discard_is_terminal(self):
        session = self._start_session(self.worksheet)
        self._ingest(self.worksheet, session)

        tk = make_target_key("analysis-1", T_WEIGHT_KEYWORD)
        session_store.assign_reading(self.worksheet, "e-1", tk)

        ok, message = session_store.discard_reading(self.worksheet, "e-1")
        self.assertTrue(ok)

        data = session_store.get_session_data(self.worksheet)
        event = data["events"]["e-1"]
        self.assertEqual(event["status"], session_store.STATUS_DISCARDED)
        # 废弃释放占用的目标位
        self.assertNotIn(tk, data["assignments"])

        # 废弃读数不可再分配
        ok, message = session_store.assign_reading(
            self.worksheet, "e-1", tk)
        self.assertFalse(ok)

    def test_set_manual_value(self):
        session = self._start_session(self.worksheet)
        tk = make_target_key("analysis-1", "T_name")
        ok, message = session_store.set_manual_value(
            self.worksheet, tk, u"Z13")
        self.assertTrue(ok)
        data = session_store.get_session_data(self.worksheet)
        assignment = data["assignments"][tk]
        self.assertEqual(assignment["source"], session_store.SOURCE_MANUAL)
        self.assertEqual(assignment["value"], u"Z13")

    def test_logs_recorded(self):
        session = self._start_session(self.worksheet)
        self._ingest(self.worksheet, session)
        tk = make_target_key("analysis-1", T_WEIGHT_KEYWORD)
        session_store.assign_reading(self.worksheet, "e-1", tk)
        session_store.unassign_reading(self.worksheet, tk)
        session_store.close_session(self.worksheet)

        data = session_store.get_session_data(self.worksheet)
        actions = [log["action"] for log in data["logs"]]
        self.assertIn("session_start", actions)
        self.assertIn("receive", actions)
        self.assertIn("assign", actions)
        self.assertIn("unassign", actions)
        self.assertIn("session_close", actions)

    def test_resolve_worksheet_by_session_id(self):
        session = self._start_session(self.worksheet)
        resolved = session_store.resolve_worksheet_by_session_id(
            self.worksheet2, session["session_id"])
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.UID(), "ws-1")
        self.assertIsNone(session_store.resolve_worksheet_by_session_id(
            self.worksheet2, "not-exists"))


@unittest.skipUnless(_IMPORT_OK, "Zope 环境不可用，跳过远端采集端模式测试")
class AgentModeSessionStoreTest(unittest.TestCase):
    """远端采集端模式（PHASE1_AGENT_MODE=True）测试

    该模式下 LIMS 不直连仪器：start_listening 只标记监听并做跨 Worksheet
    占用互斥；is_listening 不依赖 relay；stop_listening 不通知 relay。
    """

    def setUp(self):
        self._orig = {}
        self._patch("get_uid", lambda obj: obj.UID())
        self._patch("get_id", lambda obj: getattr(
            obj, "code", getattr(obj, "id", obj.UID())))
        self._patch("get_title", lambda obj: getattr(
            obj, "title", getattr(obj, "code", obj.UID())))
        self._patch("get_path", lambda obj: obj.UID())
        self._patch("is_object", lambda obj: True)
        self._orig_portal = session_store._get_portal
        self.portal = FakePortal()
        session_store._get_portal = lambda context: self.portal
        session_store.relay.CONNECTIONS.clear()
        self._orig_agent_mode = phase1_targets.PHASE1_AGENT_MODE
        phase1_targets.PHASE1_AGENT_MODE = True

        # 模拟采集端（agent）：默认连接成功，记录调用
        self._orig_notify_agent = session_store._notify_agent
        self._orig_get_tcp_addr = session_store.get_instrument_tcp_address
        self._orig_get_template = session_store.get_template_for_instrument
        self.agent_calls = []
        session_store._notify_agent = self._fake_notify_agent
        session_store.get_instrument_tcp_address = (
            lambda ws: (u"192.168.1.5", u"55097", u"模板"))
        session_store.get_template_for_instrument = (
            lambda context, code: self._fake_template())

        self.instrument = FakeInstrument("inst-1", "BALANCE-01", u"电子天平")
        self.worksheet = FakeWorksheet("ws-1", self.instrument)
        self.worksheet2 = FakeWorksheet("ws-2", self.instrument)

    def _fake_template(self):
        template = type("FakeTemplate", (), {})()
        template.agent_api_url = u"http://192.168.1.5:8090"
        return template

    def _fake_notify_agent(self, agent_url, action, payload=None, timeout=8):
        self.agent_calls.append({
            "url": agent_url,
            "action": action,
            "payload": payload or {},
        })
        return True, u"已连接 %s:%s" % (
            (payload or {}).get("host", ""), (payload or {}).get("port", ""))

    def tearDown(self):
        session_store._get_portal = self._orig_portal
        session_store.relay.CONNECTIONS.clear()
        session_store._notify_agent = self._orig_notify_agent
        session_store.get_instrument_tcp_address = self._orig_get_tcp_addr
        session_store.get_template_for_instrument = self._orig_get_template
        phase1_targets.PHASE1_AGENT_MODE = self._orig_agent_mode
        for name, original in self._orig.items():
            if original is None:
                delattr(bika_api, name)
            else:
                setattr(bika_api, name, original)

    def _patch(self, name, func):
        self._orig[name] = getattr(bika_api, name, None)
        setattr(bika_api, name, func)

    def test_start_listening_marks_session_without_relay(self):
        # agent 模式下不调用 relay / start_instrument，主动通知采集端连接
        ok, message = session_store.start_listening(self.worksheet)
        self.assertTrue(ok, message)
        self.assertTrue(session_store.is_listening(self.worksheet))
        # relay 无任何连接，is_listening 仍为 True（不依赖 relay）
        self.assertEqual(session_store.relay.CONNECTIONS, {})
        # 已调用采集端 /api/start_sync，带仪器地址与 push=true
        self.assertEqual(len(self.agent_calls), 1)
        call = self.agent_calls[0]
        self.assertEqual(call["action"], "/api/start_sync")
        self.assertEqual(call["payload"]["host"], u"192.168.1.5")
        self.assertEqual(call["payload"]["port"], 55097)
        self.assertTrue(call["payload"]["push"])

    def test_start_fails_when_agent_reports_error(self):
        # 采集端连接失败（如 TCP 通道未开）：开始采集返回失败且不置监听
        session_store._notify_agent = (
            lambda url, action, payload=None, timeout=8:
            (False, u"连接仪器 192.168.1.5:55097 失败：连接被拒绝"))
        ok, message = session_store.start_listening(self.worksheet)
        self.assertFalse(ok)
        self.assertIn(u"连接仪器", message)
        self.assertFalse(session_store.is_listening(self.worksheet))
        # 采集端不可达同样报错
        session_store._notify_agent = (
            lambda url, action, payload=None, timeout=8:
            (False, u"无法连接采集端 http://192.168.1.5:8090/api/start_sync：超时"))
        ok, message = session_store.start_listening(self.worksheet)
        self.assertFalse(ok)
        self.assertFalse(session_store.is_listening(self.worksheet))

    def test_stop_listening_notifies_agent(self):
        session_store.start_listening(self.worksheet)
        self.agent_calls = []
        ok, message = session_store.stop_listening(self.worksheet)
        self.assertTrue(ok)
        self.assertFalse(session_store.is_listening(self.worksheet))
        self.assertEqual(len(self.agent_calls), 1)
        self.assertEqual(self.agent_calls[0]["action"], "/api/stop")

    def test_cross_worksheet_occupancy_rejected(self):
        # ws-1 开始采集（监听 BALANCE-01）
        session_store.start_listening(self.worksheet)
        self.assertTrue(session_store.is_listening(self.worksheet))

        # ws-2 同一仪器开始采集：被拒（非 force）
        ok, message = session_store.start_listening(self.worksheet2)
        self.assertFalse(ok)
        self.assertIn(u"正在使用", message)
        self.assertFalse(session_store.is_listening(self.worksheet2))
        # ws-1 不受影响
        self.assertTrue(session_store.is_listening(self.worksheet))

    def test_force_preempts_other_worksheet(self):
        session_store.start_listening(self.worksheet)
        # ws-2 force 挤占
        ok, message = session_store.start_listening(
            self.worksheet2, force=True)
        self.assertTrue(ok, message)
        self.assertTrue(session_store.is_listening(self.worksheet2))
        # ws-1 监听被释放
        self.assertFalse(session_store.is_listening(self.worksheet))
        # 占用者信息同步
        data = session_store.get_session_data(self.worksheet2)
        self.assertTrue(data["active_session"].get("occupied_by"))

    def test_resolve_listening_worksheet_by_instrument(self):
        self.assertIsNone(
            session_store.resolve_listening_worksheet_by_instrument(
                self.worksheet, "BALANCE-01")[0])
        session_store.start_listening(self.worksheet)
        ws, session = session_store.resolve_listening_worksheet_by_instrument(
            self.worksheet2, "BALANCE-01")
        self.assertIsNotNone(ws)
        self.assertEqual(ws.UID(), "ws-1")
        self.assertIsNone(
            session_store.resolve_listening_worksheet_by_instrument(
                self.worksheet, "BALANCE-02")[0])


if __name__ == "__main__":
    unittest.main()
