# -*- coding: utf-8 -*-
"""Workflow guard adapter for the electronic signature MVP."""

from bika.lims.api.user import get_user_id

from maitux.esignature.services.context import (
    is_transition_execution_request,
    is_verified_signature_context_valid,
)
from maitux.esignature.services.policy import SignaturePolicyResolver


class ESignatureGuardAdapter(object):
    """Main workflow gate for signature-required transitions."""

    def __init__(self, context):
        self.context = context
        self.policy_resolver = SignaturePolicyResolver()

    def guard(self, transition):
        user_id = get_user_id()
        policy = self.policy_resolver.resolve(self.context, transition, user_id=user_id)
        if not policy.get("signature_required"):
            return True

        if not is_transition_execution_request(transition):
            # Allow the action to remain visible; the real gate happens during
            # the execution request and is reinforced by BeforeTransitionEvent.
            return True

        if not user_id:
            return False

        return is_verified_signature_context_valid(
            self.context,
            transition,
            user_id,
        )

