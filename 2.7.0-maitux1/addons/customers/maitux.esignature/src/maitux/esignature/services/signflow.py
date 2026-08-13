# -*- coding: utf-8 -*-
"""电子签名双人同页校验辅助函数。"""


def _normalize_user_id(user_id):
    return (user_id or "").strip()


def authenticate_countersign_users(provider,
                                   primary_user_id,
                                   primary_password,
                                   secondary_user_id,
                                   secondary_password,
                                   request_context=None):
    """在同一个界面里一次性校验两个操作员账号密码。"""
    primary_user_id = _normalize_user_id(primary_user_id)
    secondary_user_id = _normalize_user_id(secondary_user_id)

    if not primary_user_id:
        return {
            "authenticated": False,
            "failure_reason": "missing_primary_user_id",
        }
    if not primary_password:
        return {
            "authenticated": False,
            "failure_reason": "missing_primary_password",
        }
    if not secondary_user_id:
        return {
            "authenticated": False,
            "failure_reason": "missing_secondary_user_id",
        }
    if not secondary_password:
        return {
            "authenticated": False,
            "failure_reason": "missing_secondary_password",
        }
    if primary_user_id == secondary_user_id:
        # 双人复核必须是两个不同账号，避免同一人重复签名。
        return {
            "authenticated": False,
            "failure_reason": "same_signer_not_allowed",
        }

    primary_result = provider.authenticate_user(
        primary_user_id,
        primary_password,
        request_context=request_context,
    )
    if not primary_result.get("authenticated"):
        return {
            "authenticated": False,
            "failure_reason": "primary_auth_failed",
            "provider_failure_reason": primary_result.get("failure_reason"),
            "primary_user_id": primary_user_id,
        }

    secondary_result = provider.authenticate_user(
        secondary_user_id,
        secondary_password,
        request_context=request_context,
    )
    if not secondary_result.get("authenticated"):
        return {
            "authenticated": False,
            "failure_reason": "secondary_auth_failed",
            "provider_failure_reason": secondary_result.get("failure_reason"),
            "primary_user_id": primary_user_id,
            "secondary_user_id": secondary_user_id,
        }

    return {
        "authenticated": True,
        "failure_reason": None,
        "primary_user_id": primary_user_id,
        "secondary_user_id": secondary_user_id,
        "primary_auth_backend_id": primary_result.get("backend_id"),
        "secondary_auth_backend_id": secondary_result.get("backend_id"),
    }
