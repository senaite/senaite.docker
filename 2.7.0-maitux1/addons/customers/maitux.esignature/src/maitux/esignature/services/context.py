# -*- coding: utf-8 -*-
"""Request-scoped verified signature context helpers."""

from datetime import datetime, timedelta

from bika.lims import api
from zope.annotation.interfaces import IAnnotations


CONTEXT_KEY = "maitux.esignature.verified_signature_context"


def _get_request(request=None):
    return request or api.get_request()


def _annotations(request=None):
    request = _get_request(request)
    if request is None:
        return None
    try:
        return IAnnotations(request)
    except Exception:
        return None


def _parse_utc_datetime(value):
    if not value:
        return None

    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def build_verified_signature_context(context, transition_id, user_id, ttl_seconds=300,
                                     meaning=None, reason=None, auth_backend_id=None,
                                     signature_type=None,
                                     initiator_user_id=None,
                                     execution_user_id=None,
                                     primary_signer_user_id=None,
                                     require_countersign=False,
                                     countersigner_user_id=None,
                                     countersign_auth_backend_id=None,
                                     request=None):
    object_uid = api.get_uid(context)
    expires_at = datetime.utcnow() + timedelta(seconds=int(ttl_seconds))
    initiator_user_id = initiator_user_id or user_id
    execution_user_id = execution_user_id or user_id
    primary_signer_user_id = primary_signer_user_id or user_id
    signer_userids = [primary_signer_user_id]
    if countersigner_user_id and countersigner_user_id not in signer_userids:
        signer_userids.append(countersigner_user_id)
    return {
        "object_uid": object_uid,
        "object_path": "/".join(context.getPhysicalPath()),
        "portal_type": getattr(context, "portal_type", None),
        "transition_id": transition_id,
        "initiator_user_id": initiator_user_id,
        "execution_user_id": execution_user_id,
        "user_id": user_id,
        "primary_signer_user_id": primary_signer_user_id,
        "signer_userids": signer_userids,
        "require_countersign": bool(require_countersign),
        "countersign_completed": bool(countersigner_user_id),
        "countersigner_user_id": countersigner_user_id,
        "meaning": meaning,
        "reason": reason,
        "auth_backend_id": auth_backend_id,
        "countersign_auth_backend_id": countersign_auth_backend_id,
        "signature_type": signature_type,
        "expires_at": expires_at.isoformat() + "Z",
    }


def set_verified_signature_context(context, transition_id, user_id, ttl_seconds=300,
                                   meaning=None, reason=None, auth_backend_id=None,
                                   signature_type=None,
                                   initiator_user_id=None,
                                   execution_user_id=None,
                                   primary_signer_user_id=None,
                                   require_countersign=False,
                                   countersigner_user_id=None,
                                   countersign_auth_backend_id=None,
                                   request=None):
    annotations = _annotations(request)
    if annotations is None:
        return None

    value = build_verified_signature_context(
        context,
        transition_id,
        user_id,
        ttl_seconds=ttl_seconds,
        meaning=meaning,
        reason=reason,
        auth_backend_id=auth_backend_id,
        signature_type=signature_type,
        initiator_user_id=initiator_user_id,
        execution_user_id=execution_user_id,
        primary_signer_user_id=primary_signer_user_id,
        require_countersign=require_countersign,
        countersigner_user_id=countersigner_user_id,
        countersign_auth_backend_id=countersign_auth_backend_id,
        request=request,
    )
    annotations[CONTEXT_KEY] = value
    return value


def get_verified_signature_context(request=None):
    annotations = _annotations(request)
    if annotations is None:
        return None
    return annotations.get(CONTEXT_KEY)


def clear_verified_signature_context(request=None):
    annotations = _annotations(request)
    if annotations is None:
        return None
    return annotations.pop(CONTEXT_KEY, None)


def build_signature_summary(context_data):
    if not context_data:
        return ""

    # 瀹¤鎽樿淇濇寔鍗曡鏂囨湰锛屼究浜庣洿鎺ユ寕鍒扮幇鏈?AuditLog comments 瀛楁銆?
    pieces = [
        "Electronic signature",
        "first_signer={}".format(
            context_data.get("initiator_user_id")
            or context_data.get("primary_signer_user_id")
            or "unknown"
        ),
        "second_signer={}".format(context_data.get("countersigner_user_id") or ""),
        "execution_user={}".format(
            context_data.get("execution_user_id")
            or context_data.get("user_id")
            or "unknown"
        ),
        "countersign_required={}".format(
            "yes" if context_data.get("require_countersign") else "no"
        ),
        "transition={}".format(context_data.get("transition_id") or "unknown"),
        "signature_type={}".format(context_data.get("signature_type") or "unknown"),
        "meaning={}".format(context_data.get("meaning") or ""),
        "reason={}".format(context_data.get("reason") or ""),
        "auth_backend={}".format(context_data.get("auth_backend_id") or "unknown"),
    ]
    return "; ".join(pieces)


def is_verified_signature_context_valid(context, transition_id, user_id, request=None):
    value = get_verified_signature_context(request=request)
    if not value:
        return False

    if value.get("object_uid") != api.get_uid(context):
        return False
    if value.get("transition_id") != transition_id:
        return False
    expected_user_id = (
        value.get("execution_user_id")
        or value.get("user_id")
        or value.get("initiator_user_id")
    )
    if expected_user_id != user_id:
        return False

    if value.get("require_countersign") and not value.get("countersigner_user_id"):
        return False

    expires_at = value.get("expires_at")
    if not expires_at:
        return False

    expires_dt = _parse_utc_datetime(expires_at.rstrip("Z"))
    if expires_dt is None:
        return False

    return expires_dt >= datetime.utcnow()


def is_transition_execution_request(transition_id, request=None):
    request = _get_request(request)
    if request is None:
        return False

    requested_action = request.get("workflow_action_id") or request.get("workflow_action")
    if requested_action == transition_id:
        return True

    if request.get("execute_transition") and request.get("transition_id") == transition_id:
        return True

    return False

