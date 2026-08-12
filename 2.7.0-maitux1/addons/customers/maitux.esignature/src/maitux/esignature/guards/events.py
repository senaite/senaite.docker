# -*- coding: utf-8 -*-
"""Before-transition event handlers for the electronic signature MVP."""

from bika.lims.api.user import get_user_id
from Products.CMFCore.WorkflowCore import WorkflowException

from maitux.esignature.services.context import (
    is_verified_signature_context_valid,
)
from maitux.esignature.services.policy import SignaturePolicyResolver


def on_before_transition(context, event):
    """Supplementary check and token consumption before transition execution."""
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

