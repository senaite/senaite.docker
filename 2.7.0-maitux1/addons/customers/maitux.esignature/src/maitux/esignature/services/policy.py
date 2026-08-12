# -*- coding: utf-8 -*-
"""Minimal policy resolver for the electronic signature MVP."""

from plone import api

from maitux.esignature.services.rules import build_legacy_rule
from maitux.esignature.services.rules import loads_policy_rules


DEFAULT_POLICY = {
    "signature_required": False,
    "require_countersign": False,
    "signature_type": None,
    "meaning_required": False,
    "reason_required": False,
    "auth_backend": "pas",
    "verified_context_ttl_seconds": 300,
    "auditlog_summary_enabled": True,
    "source": "mvp_default",
}


class SignaturePolicyResolver(object):
    """Resolve the MVP policy for the configured pilot transition."""

    def __init__(self, portal=None):
        self.portal = portal or api.portal.get()

    def _registry_value(self, name, default):
        key = "maitux.esignature.{0}".format(name)
        try:
            return api.portal.get_registry_record(key, default=default)
        except Exception:
            return default

    def _current_workflow_id(self, context):
        """尽量取到对象当前绑定的 workflow id，供规则表精确匹配。"""
        workflow_tool = api.portal.get_tool("portal_workflow")
        try:
            workflows = workflow_tool.getWorkflowsFor(context) or []
        except Exception:
            workflows = []
        if not workflows:
            return ""
        workflow = workflows[0]
        getter = getattr(workflow, "getId", None)
        if callable(getter):
            try:
                return getter()
            except Exception:
                return ""
        return getattr(workflow, "id", "")

    def resolve(self, context, transition_id, user_id=None):
        portal_type = getattr(context, "portal_type", None)
        enabled = bool(self._registry_value("enabled", True))
        signature_type = self._registry_value("signature_type", "verification")
        meaning_required = bool(self._registry_value("meaning_required", True))
        reason_required = bool(self._registry_value("reason_required", True))
        verified_context_ttl_seconds = int(
            self._registry_value("verified_context_ttl_seconds", 300)
        )
        auditlog_summary_enabled = bool(
            self._registry_value("auditlog_summary_enabled", True)
        )
        settings = {
            "enabled": enabled,
            "pilot_portal_type": self._registry_value("pilot_portal_type", "Analysis"),
            "pilot_transition": self._registry_value("pilot_transition", "verify"),
            "meaning_required": meaning_required,
            "reason_required": reason_required,
        }
        policy_rules = loads_policy_rules(
            self._registry_value("policy_rules_json", u"[]"),
            legacy_rule=build_legacy_rule(settings),
        )
        workflow_id = self._current_workflow_id(context)

        policy = dict(DEFAULT_POLICY)
        policy.update({
            "enabled": enabled,
            "portal_type": portal_type,
            "transition_id": transition_id,
            "user_id": user_id,
            "pilot_portal_type": settings["pilot_portal_type"],
            "pilot_transition": settings["pilot_transition"],
            "signature_type": signature_type,
            "meaning_required": meaning_required,
            "reason_required": reason_required,
            "verified_context_ttl_seconds": verified_context_ttl_seconds,
            "auditlog_summary_enabled": auditlog_summary_enabled,
            "workflow_id": workflow_id,
            "policy_rules_count": len(policy_rules),
        })

        if not enabled:
            return policy

        for rule in policy_rules:
            if rule.get("portal_type") != portal_type:
                continue
            if rule.get("transition_id") != transition_id:
                continue
            if rule.get("workflow_id") and workflow_id:
                if rule.get("workflow_id") != workflow_id:
                    continue

            policy.update({
                "signature_required": rule.get("signature_required", True),
                "require_countersign": rule.get("require_countersign", False),
                "meaning_required": rule.get("meaning_required", meaning_required),
                "reason_required": rule.get("reason_required", reason_required),
                "auth_backend": "pas",
                "source": "rules_table",
            })
            return policy
        return policy

