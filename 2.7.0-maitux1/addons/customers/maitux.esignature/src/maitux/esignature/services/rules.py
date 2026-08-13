# -*- coding: utf-8 -*-
"""电子签名规则表的序列化与兼容辅助函数。"""

import json


try:  # pragma: no cover
    text_type = unicode
except NameError:  # pragma: no cover
    text_type = str


def _as_text(value):
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


def _as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    value = _as_text(value).strip().lower()
    if value in (u"1", u"true", u"yes", u"on"):
        return True
    if value in (u"0", u"false", u"no", u"off"):
        return False
    return default


def normalize_rule(rule, defaults=None):
    """将任意输入规则归一化成统一结构。"""
    defaults = defaults or {}
    rule = rule or {}
    normalized = {
        "portal_type": _as_text(rule.get("portal_type")).strip(),
        "workflow_id": _as_text(rule.get("workflow_id")).strip(),
        "transition_id": _as_text(rule.get("transition_id")).strip(),
        "signature_required": _as_bool(
            rule.get("signature_required"),
            defaults.get("signature_required", True),
        ),
        "require_countersign": _as_bool(
            rule.get("require_countersign"),
            defaults.get("require_countersign", False),
        ),
        "meaning_required": _as_bool(
            rule.get("meaning_required"),
            defaults.get("meaning_required", True),
        ),
        "reason_required": _as_bool(
            rule.get("reason_required"),
            defaults.get("reason_required", True),
        ),
    }
    return normalized


def build_legacy_rule(settings):
    """把旧版单条 pilot 配置转换为规则表中的一行。"""
    settings = settings or {}
    portal_type = _as_text(settings.get("pilot_portal_type")).strip()
    transition_id = _as_text(settings.get("pilot_transition")).strip()
    if not portal_type or not transition_id:
        return None
    return normalize_rule({
        "portal_type": portal_type,
        "workflow_id": _as_text(settings.get("workflow_id")).strip(),
        "transition_id": transition_id,
        "signature_required": settings.get("enabled", True),
        "require_countersign": False,
        "meaning_required": settings.get("meaning_required", True),
        "reason_required": settings.get("reason_required", True),
    })


def loads_policy_rules(raw_value, legacy_rule=None):
    """从 registry 文本中读取规则表，并兼容旧版单条配置。"""
    rules = []
    if raw_value:
        try:
            data = json.loads(raw_value)
        except Exception:
            data = []
        if isinstance(data, list):
            for item in data:
                normalized = normalize_rule(item)
                if normalized.get("portal_type") and normalized.get("transition_id"):
                    rules.append(normalized)

    if not rules and legacy_rule:
        rules.append(normalize_rule(legacy_rule))
    return rules


def dumps_policy_rules(rules):
    """把规则表序列化为 registry 可保存的 JSON 文本。"""
    items = []
    for rule in rules or []:
        normalized = normalize_rule(rule)
        if normalized.get("portal_type") and normalized.get("transition_id"):
            items.append(normalized)
    return _as_text(json.dumps(items, ensure_ascii=False, sort_keys=True))
