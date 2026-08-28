# -*- coding: utf-8 -*-
import importlib.util
import os
import sys
import types
import unittest


def load_signflow_module():
    """加载 signflow 模块。"""
    file_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "services", "signflow.py"))
    spec = importlib.util.spec_from_file_location("test_signflow_module", file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_auditlog_module():
    """加载 auditlog 模块，并替换外部依赖。"""
    api_module = types.SimpleNamespace(
        get_uid=lambda obj: getattr(obj, "uid", ""),
        get_portal=lambda: object(),
    )

    snapshot_storage = []
    snapshot_module = types.ModuleType("bika.lims.api.snapshot")
    snapshot_module.get_storage = lambda obj: snapshot_storage
    snapshot_module.take_snapshot = lambda *args, **kwargs: {
        "__metadata__": {},
        "action": kwargs.get("action"),
        "comments": kwargs.get("comments"),
        "esignature": kwargs.get("esignature"),
    }

    user_module = types.ModuleType("bika.lims.api.user")
    user_module.get_user_id = lambda: "session_user"

    audit_subscriber_module = types.ModuleType("bika.lims.subscribers.auditlog")
    audit_subscriber_module.reindex_object = lambda obj: None

    sys.modules["bika"] = types.ModuleType("bika")
    sys.modules["bika.lims"] = types.ModuleType("bika.lims")
    sys.modules["bika.lims"].api = api_module
    sys.modules["bika.lims.api"] = api_module
    sys.modules["bika.lims.api.snapshot"] = snapshot_module
    sys.modules["bika.lims.api.user"] = user_module
    sys.modules["bika.lims.subscribers"] = types.ModuleType("bika.lims.subscribers")
    sys.modules["bika.lims.subscribers.auditlog"] = audit_subscriber_module

    context_module = types.ModuleType("maitux.esignature.services.context")
    context_module.build_signature_summary = (
        lambda data: u"summary:{}:{}".format(
            data.get("primary_signer_user_id") or "",
            data.get("countersigner_user_id") or "",
        )
    )
    context_module.clear_verified_signature_context = lambda request=None: None
    # Records which objects the audit subscriber marked as done, so a test can
    # assert that a batch is consumed one object at a time instead of the
    # context being torn down by the first success.
    context_module.consumed = []
    context_module.consume_verified_signature_context = (
        lambda context, request=None: context_module.consumed.append(context)
    )
    context_module.get_verified_signature_context = lambda request=None: {
        "object_uid": "UID-1",
        "object_path": "/portal/item",
        "transition_id": "verify",
        "user_id": "session_user",
        "execution_user_id": "session_user",
        "initiator_user_id": "op1",
        "primary_signer_user_id": "op1",
        "countersigner_user_id": "op2",
        "require_countersign": True,
        "signature_type": "verification",
        "meaning": "approve",
        "reason": "double check",
        "status": "applied",
        "auth_backend_id": "pas",
        "countersign_auth_backend_id": "pas",
    }
    context_module.is_verified_signature_context_valid = (
        lambda context, action, user_id, request=None: True
    )
    sys.modules["maitux"] = types.ModuleType("maitux")
    sys.modules["maitux.esignature"] = types.ModuleType("maitux.esignature")
    sys.modules["maitux.esignature.services"] = types.ModuleType("maitux.esignature.services")
    sys.modules["maitux.esignature.services.context"] = context_module

    # auditlog 现在会先问「本站点装了 esignature 吗」。这里做成可切换的桩，
    # 默认 True 走原有路径，未安装的分支由 test 自己翻转。
    siteinstall_module = types.ModuleType("maitux.esignature.siteinstall")
    siteinstall_module.installed = True
    siteinstall_module.is_installed_in_current_site = (
        lambda: siteinstall_module.installed
    )
    sys.modules["maitux.esignature.siteinstall"] = siteinstall_module

    policy_module = types.ModuleType("maitux.esignature.services.policy")
    class DummyResolver(object):
        def resolve(self, context, action, user_id=None):
            return {
                "signature_required": True,
                "auditlog_summary_enabled": True,
            }
    policy_module.SignaturePolicyResolver = DummyResolver
    sys.modules["maitux.esignature.services.policy"] = policy_module

    store_module = types.ModuleType("maitux.esignature.storage.store")
    class DummyStore(object):
        def __init__(self, portal):
            self.saved = []
        def save(self, record):
            self.saved.append(dict(record))
            return dict(record)
    store_module.SignatureRecordStore = DummyStore
    sys.modules["maitux.esignature.storage"] = types.ModuleType("maitux.esignature.storage")
    sys.modules["maitux.esignature.storage.store"] = store_module

    file_path = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "adapters", "auditlog.py"))
    spec = importlib.util.spec_from_file_location("test_auditlog_module", file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._test_snapshot_storage = snapshot_storage
    module._test_siteinstall = siteinstall_module
    return module


class DummyProvider(object):
    """模拟双人签名认证结果。"""

    def __init__(self, results):
        self.results = results
        self.calls = []

    def authenticate_user(self, user_id, password, request_context=None):
        self.calls.append((user_id, password))
        return self.results.get(user_id, {
            "authenticated": False,
            "backend_id": "pas",
            "failure_reason": "invalid_credentials",
        })


class DummyContext(object):
    uid = "UID-1"
    portal_type = "Analysis"

    def getPhysicalPath(self):
        return ("", "portal", "item")


class DummyEvent(object):
    action = "verify"


class TestSignatureFlow(unittest.TestCase):

    def test_same_screen_countersign_requires_two_distinct_users(self):
        """双人复核必须在同页输入两个不同操作员账号。"""
        signflow = load_signflow_module()
        provider = DummyProvider({
            "op1": {
                "authenticated": True,
                "backend_id": "pas",
                "failure_reason": None,
            },
        })

        result = signflow.authenticate_countersign_users(
            provider,
            primary_user_id="op1",
            primary_password="pw1",
            secondary_user_id="op1",
            secondary_password="pw2",
        )

        self.assertFalse(result["authenticated"])
        self.assertEqual(result["failure_reason"], "same_signer_not_allowed")

    def test_same_screen_countersign_authenticates_both_users_once(self):
        """同页双签时应一次性校验两个操作员账号密码。"""
        signflow = load_signflow_module()
        provider = DummyProvider({
            "op1": {
                "authenticated": True,
                "backend_id": "pas",
                "failure_reason": None,
            },
            "op2": {
                "authenticated": True,
                "backend_id": "pas",
                "failure_reason": None,
            },
        })

        result = signflow.authenticate_countersign_users(
            provider,
            primary_user_id="op1",
            primary_password="pw1",
            secondary_user_id="op2",
            secondary_password="pw2",
        )

        self.assertTrue(result["authenticated"])
        self.assertEqual(result["primary_user_id"], "op1")
        self.assertEqual(result["secondary_user_id"], "op2")
        self.assertEqual(provider.calls, [("op1", "pw1"), ("op2", "pw2")])

    def test_success_auditlog_does_not_append_extra_signature_snapshot(self):
        """成功签名后只更新当前工作流审计项，不再新增独立电子签名记录。"""
        auditlog = load_auditlog_module()
        auditlog._test_snapshot_storage.append('{"__metadata__": {"comments": ""}}')

        auditlog.on_action_succeeded(DummyContext(), DummyEvent())

        self.assertEqual(len(auditlog._test_snapshot_storage), 1)

    def test_success_consumes_only_the_current_object(self):
        """成功一个对象只销掉它自己，不清空整批的已验证签名上下文。

        过去这里是无条件 clear_verified_signature_context()，批量签名时
        第 2 个对象的 guard 必然失败。
        """
        auditlog = load_auditlog_module()
        auditlog._test_snapshot_storage.append('{"__metadata__": {"comments": ""}}')
        context_module = sys.modules["maitux.esignature.services.context"]
        context_module.consumed = []

        one = DummyContext()
        auditlog.on_action_succeeded(one, DummyEvent())

        self.assertEqual(context_module.consumed, [one])

    def test_not_installed_site_writes_nothing(self):
        """本订阅器是 for="*" 的进程级注册，所有站点都会调到。

        未装本 addon 的站点不该被写入签名记录或审计快照 —— 这里断言的是
        跨站点污染的收口，不是签名逻辑本身。
        """
        auditlog = load_auditlog_module()
        auditlog._test_siteinstall.installed = False
        auditlog._test_snapshot_storage.append('{"__metadata__": {"comments": ""}}')
        context_module = sys.modules["maitux.esignature.services.context"]
        context_module.consumed = []

        auditlog.on_action_succeeded(DummyContext(), DummyEvent())

        # 审计快照原样未动，也没有任何对象被 consume
        self.assertEqual(
            auditlog._test_snapshot_storage,
            ['{"__metadata__": {"comments": ""}}'])
        self.assertEqual(context_module.consumed, [])


class TestVerifiedSignatureContext(unittest.TestCase):
    """针对 services/context.py 真实实现的批量语义测试。"""

    def load_context_module(self):
        api_module = types.ModuleType("bika.lims.api")
        api_module.get_uid = lambda obj: obj.uid
        # Must be truthy: _annotations() bails out on a None request, which
        # would silently make every set/get a no-op.
        fake_request = object()
        api_module.get_request = lambda: fake_request

        annotations_module = types.ModuleType("zope.annotation.interfaces")
        store = {}
        annotations_module.IAnnotations = lambda request: store

        sys.modules["bika"] = types.ModuleType("bika")
        sys.modules["bika.lims"] = types.ModuleType("bika.lims")
        sys.modules["bika.lims"].api = api_module
        sys.modules["bika.lims.api"] = api_module
        sys.modules["zope"] = types.ModuleType("zope")
        sys.modules["zope.annotation"] = types.ModuleType("zope.annotation")
        sys.modules["zope.annotation.interfaces"] = annotations_module

        file_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "services", "context.py"))
        spec = importlib.util.spec_from_file_location("test_context_module", file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def make(self, uid):
        obj = DummyContext()
        obj.uid = uid
        return obj

    def test_batch_context_validates_for_every_member(self):
        ctx = self.load_context_module()
        anchor, second, third = self.make("A"), self.make("B"), self.make("C")

        ctx.set_verified_signature_context(
            anchor, "reject", "op1", object_uids=["A", "B", "C"])

        for obj in (anchor, second, third):
            self.assertTrue(
                ctx.is_verified_signature_context_valid(obj, "reject", "op1"),
                "%s should be authorised by the batch signature" % obj.uid)

    def test_outsider_is_not_authorised(self):
        ctx = self.load_context_module()
        ctx.set_verified_signature_context(
            self.make("A"), "reject", "op1", object_uids=["A", "B"])

        self.assertFalse(
            ctx.is_verified_signature_context_valid(self.make("Z"), "reject", "op1"))

    def test_context_survives_until_the_last_object_is_consumed(self):
        ctx = self.load_context_module()
        anchor, second = self.make("A"), self.make("B")
        ctx.set_verified_signature_context(
            anchor, "reject", "op1", object_uids=["A", "B"])

        remaining = ctx.consume_verified_signature_context(anchor)
        self.assertEqual(remaining, 1)
        # The second object must still pass its guard after the first succeeded
        self.assertTrue(
            ctx.is_verified_signature_context_valid(second, "reject", "op1"))

        remaining = ctx.consume_verified_signature_context(second)
        self.assertEqual(remaining, 0)
        self.assertIsNone(ctx.get_verified_signature_context())

    def test_legacy_single_uid_context_still_validates(self):
        """批量之前写下的上下文只有 object_uid，仍须被认。"""
        ctx = self.load_context_module()
        ctx.set_verified_signature_context(self.make("A"), "reject", "op1")
        value = ctx.get_verified_signature_context()
        del value["object_uids"]

        self.assertTrue(
            ctx.is_verified_signature_context_valid(self.make("A"), "reject", "op1"))

    def test_countersign_covers_the_whole_batch(self):
        """一次复签覆盖整批：每个成员都认同一个 countersigner。"""
        ctx = self.load_context_module()
        ctx.set_verified_signature_context(
            self.make("A"), "reject", "op1",
            object_uids=["A", "B"],
            require_countersign=True,
            countersigner_user_id="op2",
        )

        for uid in ("A", "B"):
            self.assertTrue(
                ctx.is_verified_signature_context_valid(self.make(uid), "reject", "op1"))

    def test_countersign_required_but_missing_blocks_every_member(self):
        ctx = self.load_context_module()
        ctx.set_verified_signature_context(
            self.make("A"), "reject", "op1",
            object_uids=["A", "B"],
            require_countersign=True,
        )

        for uid in ("A", "B"):
            self.assertFalse(
                ctx.is_verified_signature_context_valid(self.make(uid), "reject", "op1"))


if __name__ == "__main__":
    unittest.main()
