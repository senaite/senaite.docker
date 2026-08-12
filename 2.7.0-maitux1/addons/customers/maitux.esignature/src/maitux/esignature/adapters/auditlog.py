# -*- coding: utf-8 -*-
"""AuditLog and signature record integration for successful transitions."""

import json

from bika.lims import api
from bika.lims.api.snapshot import get_storage as get_snapshot_storage
from bika.lims.api.snapshot import take_snapshot
from bika.lims.api.user import get_user_id
from bika.lims.subscribers.auditlog import reindex_object

from maitux.esignature.services.context import (
    build_signature_summary,
    clear_verified_signature_context,
    get_verified_signature_context,
    is_verified_signature_context_valid,
)
from maitux.esignature.services.policy import SignaturePolicyResolver
from maitux.esignature.storage.store import SignatureRecordStore


def _build_esignature_metadata(verified_context, action):
    return {
        "enabled": True,
        "signature_id": verified_context.get("signature_id"),
        "initiator_user_id": verified_context.get("initiator_user_id"),
        "user_id": verified_context.get("user_id"),
        "primary_signer_user_id": verified_context.get("primary_signer_user_id"),
        "signer_userids": verified_context.get("signer_userids") or [],
        "transition_id": verified_context.get("transition_id"),
        "signature_type": verified_context.get("signature_type"),
        "require_countersign": verified_context.get("require_countersign", False),
        "countersign_completed": verified_context.get("countersign_completed", False),
        "countersigner_user_id": verified_context.get("countersigner_user_id"),
        "meaning": verified_context.get("meaning"),
        "reason": verified_context.get("reason"),
        "auth_backend_id": verified_context.get("auth_backend_id"),
        "countersign_auth_backend_id": verified_context.get("countersign_auth_backend_id"),
        "description": build_signature_summary(verified_context),
        "status": verified_context.get("status") or "applied",
        "audit_action": "electronic_signature_{}".format(
            verified_context.get("transition_id") or action
        ),
    }


def _update_latest_snapshot(obj, verified_context, action):
    storage = get_snapshot_storage(obj)
    if not storage:
        return

    latest = json.loads(storage[-1])
    metadata = latest.get("__metadata__", {})
    metadata["comments"] = build_signature_summary(verified_context)
    metadata["esignature"] = _build_esignature_metadata(verified_context, action)
    latest["__metadata__"] = metadata
    storage[-1] = json.dumps(latest)


def _build_signature_record(obj, verified_context, action):
    return {
        "object_uid": api.get_uid(obj),
        "object_path": verified_context.get("object_path") or "/".join(obj.getPhysicalPath()),
        "portal_type": getattr(obj, "portal_type", None),
        "transition_id": verified_context.get("transition_id") or action,
        "signature_type": verified_context.get("signature_type") or "verification",
        "meaning": verified_context.get("meaning"),
        "reason": verified_context.get("reason"),
        "initiator_userid": verified_context.get("initiator_user_id") or get_user_id(),
        "signer_userid": verified_context.get("user_id") or get_user_id(),
        "primary_signer_userid": verified_context.get("primary_signer_user_id")
        or verified_context.get("user_id")
        or get_user_id(),
        "require_countersign": bool(verified_context.get("require_countersign")),
        "countersigner_userid": verified_context.get("countersigner_user_id"),
        "auth_backend_id": verified_context.get("auth_backend_id"),
        "countersign_auth_backend_id": verified_context.get("countersign_auth_backend_id"),
        "status": verified_context.get("status") or "applied",
        "auditlog_summary": build_signature_summary(verified_context),
    }


def _append_signature_audit_snapshot(obj, verified_context, action, audit_action=None):
    """为电子签名单独追加一条审计快照，便于在 Audit Log 中直接查看。"""
    signer_userid = verified_context.get("user_id") or get_user_id()
    # 这里单独追加一条 snapshot，而不是只改最后一条记录，
    # 目的是让审计轨迹中出现一条独立的电子签名日志。
    snapshot = take_snapshot(
        obj,
        store=False,
        action=audit_action or "electronic_signature_{}".format(
            verified_context.get("transition_id") or action
        ),
        actor=signer_userid,
        comments=build_signature_summary(verified_context),
        esignature=_build_esignature_metadata(verified_context, action),
    )
    snapshot.update({
        "Electronic Signature Initiator": (
            verified_context.get("initiator_user_id") or signer_userid
        ),
        "Electronic Signature Signer": signer_userid,
        "Electronic Signature Countersign Required": (
            "Yes" if verified_context.get("require_countersign") else "No"
        ),
        "Electronic Signature Countersigner": (
            verified_context.get("countersigner_user_id") or ""
        ),
        "Electronic Signature Status": verified_context.get("status") or "applied",
        "Electronic Signature Transition": verified_context.get("transition_id") or action,
        "Electronic Signature Type": verified_context.get("signature_type") or "verification",
        "Electronic Signature Meaning": verified_context.get("meaning") or "",
        "Electronic Signature Reason": verified_context.get("reason") or "",
        "Electronic Signature Description": build_signature_summary(verified_context),
    })
    get_snapshot_storage(obj).append(json.dumps(snapshot))


def record_pending_countersign(context, verified_context, action):
    """记录第一人已签、等待第二人复核的状态和审计轨迹。"""
    portal = api.get_portal()
    store = SignatureRecordStore(portal)
    data = dict(verified_context)
    data["status"] = "pending_countersign"
    record = _build_signature_record(context, data, action)
    store.save(record)
    # 仅保留业务签名记录，不再额外追加独立审计快照，避免审计追踪重复显示。
    reindex_object(context)


def on_action_succeeded(context, event):
    """Persist the signature record and enrich the latest audit snapshot."""
    action = getattr(event, "action", None)
    if not action:
        return

    user_id = get_user_id()
    policy = SignaturePolicyResolver().resolve(context, action, user_id=user_id)
    if not policy.get("signature_required"):
        return

    verified_context = get_verified_signature_context()
    if not verified_context:
        return

    if not is_verified_signature_context_valid(context, action, user_id):
        clear_verified_signature_context()
        return

    portal = api.get_portal()
    store = SignatureRecordStore(portal)
    record = _build_signature_record(context, verified_context, action)
    stored = store.save(record)

    # 正式记录始终保留；若现场仍希望保留 metadata 摘要，则继续附加到最新审计项。
    if policy.get("auditlog_summary_enabled", True):
        _update_latest_snapshot(context, dict(stored), action)
    reindex_object(context)
    clear_verified_signature_context()
