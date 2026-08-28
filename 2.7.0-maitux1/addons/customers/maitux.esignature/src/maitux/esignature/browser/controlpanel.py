# -*- coding: utf-8 -*-
"""Control panel view for the MEDAI  electronic signature add-on."""

import json

from bika.lims import api
from plone.registry.interfaces import IRegistry
from Products.Five.browser import BrowserView
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from zope.component import getUtilitiesFor
from zope.component import getUtility

from maitux.esignature.interfaces import IESignatureControlPanelSettings
from maitux.esignature.interfaces import IReAuthenticationProvider
from maitux.esignature.services.rules import build_legacy_rule
from maitux.esignature.services.rules import DEFAULT_MEANINGS
from maitux.esignature.services.rules import dumps_meaning_vocabulary
from maitux.esignature.services.rules import dumps_policy_rules
from maitux.esignature.services.rules import parse_meaning_vocabulary
from maitux.esignature.services.rules import loads_policy_rules


REGISTRY_PREFIX = "maitux.esignature"
DEFAULT_AUDITLOG_SUMMARY_ENABLED = True
DEFAULT_VERIFIED_CONTEXT_TTL_SECONDS = 300
DEFAULT_SIGNATURE_TYPE = u"verification"

try:  # pragma: no cover
    text_type = unicode
    binary_type = str
except NameError:  # pragma: no cover
    text_type = str
    binary_type = bytes


class ESignatureControlPanelView(BrowserView):
    """表格式电子签名配置页，支持增删改规则。"""

    index = ViewPageTemplateFile("templates/controlpanel.pt")

    def __call__(self):
        self._ensure_registry_records()
        if self.request.get("saved"):
            self._show_message("Electronic signature table configuration saved.", "info")
        if self.request.get("form.cancel"):
            return self.request.response.redirect(api.get_url(self.context))
        if self.request.get("form.save"):
            return self.handle_save()
        return self.index()

    def _ensure_registry_records(self):
        """确保老站点也能补齐新增的 registry 字段。"""
        registry = getUtility(IRegistry)
        try:
            registry.registerInterface(
                IESignatureControlPanelSettings,
                prefix=REGISTRY_PREFIX,
            )
        except Exception:
            pass

    def _show_message(self, message, level="info"):
        api.get_portal().plone_utils.addPortalMessage(message, level)

    def _record_key(self, name):
        return "{}.{}".format(REGISTRY_PREFIX, name)

    def _registry_value(self, name, default=None):
        registry = getUtility(IRegistry)
        record = registry.records.get(self._record_key(name))
        if record is None:
            return default
        return getattr(record, "value", default)

    def _set_registry_value(self, name, value):
        registry = getUtility(IRegistry)
        key = self._record_key(name)
        if key not in registry.records:
            registry.registerInterface(
                IESignatureControlPanelSettings,
                prefix=REGISTRY_PREFIX,
            )
        record = registry.records[key]
        record.value = self._coerce_registry_value(record, value)

    def enabled(self):
        return bool(self._registry_value("enabled", True))

    def auditlog_summary_enabled(self):
        return bool(
            self._registry_value(
                "auditlog_summary_enabled",
                DEFAULT_AUDITLOG_SUMMARY_ENABLED,
            )
        )

    def verified_context_ttl_seconds(self):
        return int(
            self._registry_value(
                "verified_context_ttl_seconds",
                DEFAULT_VERIFIED_CONTEXT_TTL_SECONDS,
            ) or DEFAULT_VERIFIED_CONTEXT_TTL_SECONDS
        )

    def signature_type(self):
        return (
            self._registry_value("signature_type", DEFAULT_SIGNATURE_TYPE)
            or DEFAULT_SIGNATURE_TYPE
        )

    def _legacy_settings(self):
        return {
            "enabled": self.enabled(),
            "pilot_portal_type": self._registry_value("pilot_portal_type", u"Analysis"),
            "pilot_transition": self._registry_value("pilot_transition", u"verify"),
            "meaning_required": bool(self._registry_value("meaning_required", True)),
            "reason_required": bool(self._registry_value("reason_required", True)),
            "workflow_id": u"",
        }

    def current_rules(self):
        return loads_policy_rules(
            self._registry_value("policy_rules_json", u"[]"),
            legacy_rule=build_legacy_rule(self._legacy_settings()),
        )

    def current_rules_json(self):
        return json.dumps(self.current_rules(), ensure_ascii=False)

    def workflow_catalog(self):
        """把对象类型、工作流、节点整理成前端下拉需要的结构。"""
        portal_types_tool = api.get_tool("portal_types")
        workflow_tool = api.get_tool("portal_workflow")
        portal_types = []
        workflow_map = {}
        portal_type_workflows = {}

        for workflow in workflow_tool.objectValues():
            if not getattr(workflow, "transitions", None):
                continue
            workflow_id = self._object_id(workflow)
            transitions = []
            for transition in workflow.transitions.objectValues():
                transition_id = self._object_id(transition)
                if not transition_id:
                    continue
                transitions.append({
                    "id": transition_id,
                    "title": self._transition_title(transition),
                })
            workflow_map[workflow_id] = {
                "id": workflow_id,
                "title": self._workflow_title(workflow),
                "transitions": sorted(
                    transitions,
                    key=lambda item: item.get("title") or item.get("id"),
                ),
            }

        for fti in portal_types_tool.listTypeInfo():
            portal_type = self._object_id(fti)
            if not portal_type:
                continue
            portal_types.append({
                "id": portal_type,
                "title": self._fti_title(fti),
            })
            portal_type_workflows[portal_type] = self._workflow_ids_for_portal_type(
                workflow_tool,
                portal_type,
                workflow_map,
            )

        portal_types = sorted(
            portal_types,
            key=lambda item: item.get("title") or item.get("id"),
        )
        return {
            "portal_types": portal_types,
            "workflows": workflow_map,
            "portal_type_workflows": portal_type_workflows,
        }

    def auth_backends(self):
        """Registered re-authentication providers, for the settings dropdown.

        Enumerated rather than hardcoded: an SSO add-on registers its own
        named utility and shows up here without this package knowing it.
        """
        items = []
        for name, provider in getUtilitiesFor(IReAuthenticationProvider):
            items.append({
                "id": name,
                "title": getattr(provider, "title", None) or name,
            })
        return sorted(items, key=lambda item: item["title"])

    def auth_backend(self):
        """The configured backend id, defaulting to the local accounts."""
        return self._registry_value("auth_backend", u"pas") or u"pas"

    def meaning_vocabulary(self):
        """The configured list of signature meanings."""
        return parse_meaning_vocabulary(
            self._registry_value("meaning_vocabulary", u""))

    def meaning_vocabulary_text(self):
        """The vocabulary as the textarea shows it, one per line."""
        return u"\n".join(self.meaning_vocabulary())

    def meaning_vocabulary_json(self):
        """The vocabulary for the rule table dropdowns."""
        return json.dumps(self.meaning_vocabulary(), ensure_ascii=False)

    def default_meanings_json(self):
        """Suggested meaning per transition, for the rule table.

        Served from services/rules.py rather than duplicated in the template,
        so what the admin is offered and what the signature policy falls back
        to cannot drift apart.
        """
        return json.dumps(DEFAULT_MEANINGS, ensure_ascii=False, sort_keys=True)

    def workflow_catalog_json(self):
        return json.dumps(self.workflow_catalog(), ensure_ascii=False)

    def handle_save(self):
        """保存基础参数和规则表，并同步旧版单条配置字段。"""
        raw_rules = self.request.get("rules_payload", u"[]")
        try:
            parsed_rules = json.loads(raw_rules or u"[]")
        except Exception:
            self._show_message(
                "Rule table data is invalid. Please refresh the page and try again.",
                "error",
            )
            return self.index()

        rules = loads_policy_rules(dumps_policy_rules(parsed_rules))
        self._set_registry_value("enabled", bool(self.request.get("enabled")))
        # 这三个基础字段已经在界面隐藏，保存时强制回写固定默认值。
        self._set_registry_value(
            "auditlog_summary_enabled",
            DEFAULT_AUDITLOG_SUMMARY_ENABLED,
        )
        self._set_registry_value(
            "verified_context_ttl_seconds",
            DEFAULT_VERIFIED_CONTEXT_TTL_SECONDS,
        )
        self._set_registry_value("signature_type", DEFAULT_SIGNATURE_TYPE)
        self._set_registry_value("policy_rules_json", dumps_policy_rules(rules))
        self._set_registry_value(
            "auth_backend",
            self._string_value(self.request.get("auth_backend", u"")) or u"pas",
        )
        self._set_registry_value(
            "meaning_vocabulary",
            dumps_meaning_vocabulary(
                parse_meaning_vocabulary(
                    self.request.get("meaning_vocabulary", u""))),
        )

        # 为兼容旧逻辑和已有概览页，继续把第一条有效规则同步回单条 pilot 字段。
        first_rule = rules[0] if rules else None
        if first_rule is not None:
            self._set_registry_value(
                "pilot_portal_type",
                self._string_value(first_rule.get("portal_type", u"")),
            )
            self._set_registry_value(
                "pilot_transition",
                self._string_value(first_rule.get("transition_id", u"")),
            )
            self._set_registry_value(
                "meaning_required",
                first_rule.get("meaning_required", True),
            )
            self._set_registry_value(
                "reason_required",
                first_rule.get("reason_required", True),
            )

        return self.request.response.redirect(
            "{}/@@maitux-esignature-controlpanel?saved=1".format(api.get_url(self.context))
        )

    def _workflow_ids_for_portal_type(self, workflow_tool, portal_type, workflow_map):
        workflow_ids = []
        getters = (
            "getChainForPortalType",
            "getDefaultChainFor",
            "getChainFor",
        )
        for name in getters:
            getter = getattr(workflow_tool, name, None)
            if getter is None:
                continue
            try:
                value = getter(portal_type)
            except TypeError:
                continue
            except Exception:
                value = None
            workflow_ids = self._extract_workflow_ids(value)
            if workflow_ids:
                break

        if not workflow_ids:
            workflow_ids = sorted(workflow_map.keys())
        return [wf_id for wf_id in workflow_ids if wf_id in workflow_map]

    def _extract_workflow_ids(self, value):
        if not value:
            return []
        if isinstance(value, (list, tuple)):
            return [self._string_value(item) for item in value if self._string_value(item)]
        text = self._string_value(value)
        if not text:
            return []
        return [item.strip() for item in text.split(",") if item.strip()]

    def _string_value(self, value):
        if value is None:
            return u""
        if isinstance(value, text_type):
            return value
        try:
            return value.decode("utf-8")
        except Exception:
            try:
                return text_type(value)
            except Exception:
                return u""

    def _coerce_registry_value(self, record, value):
        """按 registry 字段类型统一做值转换，兼容 Python 2/Plone 老环境。"""
        field = getattr(record, "field", None)
        field_name = field.__class__.__name__ if field is not None else ""

        if field_name in ("Text", "TextLine"):
            return self._string_value(value)

        if field_name == "Bool":
            return bool(value)

        if field_name == "Int":
            try:
                return int(value)
            except Exception:
                return 0

        if isinstance(value, binary_type):
            return self._string_value(value)
        return value

    def _object_id(self, obj):
        getter = getattr(obj, "getId", None)
        if callable(getter):
            try:
                return self._string_value(getter())
            except Exception:
                return self._string_value(getattr(obj, "id", u""))
        return self._string_value(getattr(obj, "id", u""))

    def _fti_title(self, fti):
        title_getter = getattr(fti, "Title", None)
        if callable(title_getter):
            try:
                title = title_getter()
            except Exception:
                title = None
            if title:
                return self._string_value(title)
        return self._object_id(fti)

    def _workflow_title(self, workflow):
        title = getattr(workflow, "title", None)
        if title:
            return self._string_value(title)
        title_getter = getattr(workflow, "Title", None)
        if callable(title_getter):
            try:
                title = title_getter()
            except Exception:
                title = None
            if title:
                return self._string_value(title)
        return self._object_id(workflow)

    def _transition_title(self, transition):
        title = getattr(transition, "title", None)
        if title:
            return self._string_value(title)
        title_getter = getattr(transition, "Title", None)
        if callable(title_getter):
            try:
                title = title_getter()
            except Exception:
                title = None
            if title:
                return self._string_value(title)
        return self._object_id(transition)
