# -*- coding: utf-8 -*-
"""Before-transition event handlers for the electronic signature MVP."""

from bika.lims.api.user import get_user_id
from Products.CMFCore.WorkflowCore import WorkflowException

from maitux.esignature.services.context import (
    is_verified_signature_context_valid,
)
from maitux.esignature.services.policy import SignaturePolicyResolver
from maitux.esignature.siteinstall import is_installed_in_current_site


def on_before_transition(context, event):
    """Supplementary check and token consumption before transition execution."""
    # 本订阅器是 for="*" 的进程级注册，所有站点的每一次 transition 都会调到，
    # 而它会 raise WorkflowException —— 是真正会把未安装站点拦死的那一环。
    # 未装本 addon 的站点直接不参与。详见 siteinstall。
    if not is_installed_in_current_site():
        return

    transition = getattr(event, "transition", None)
    if transition is None:
        return

    transition_id = getattr(transition, "id", None)
    if not transition_id:
        return

    user_id = get_user_id()
    policy = SignaturePolicyResolver().resolve(context, transition_id, user_id=user_id)
    if not policy.get("signature_required"):
        return

    if not is_verified_signature_context_valid(context, transition_id, user_id):
        raise WorkflowException(
            "Electronic signature verification is required before transition '{}'.".format(
                transition_id
            )
        )

