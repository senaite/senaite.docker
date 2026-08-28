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


#: 各 transition 的默认签名含义。
#:
#: 含义描述的不是「结果是什么」，而是签名人相对这条记录扮演什么角色 ——
#: 批准还是拒绝由点击哪个 transition 决定，含义回答的是另一个问题。所以
#: reject 配 "Approval" 是荒谬的，配 "Responsibility"（为这个决定负责）才通顺。
#:
#: 21 CFR Part 11 §11.50(a)(3) 要求签名 manifestation 载明含义，原文用的是
#: "such as review, approval, responsibility, or authorship" —— 是举例而非
#: 强制词表，现场可按内部 SOP 改写。这里只提供建议默认值。
DEFAULT_MEANINGS = {
    u"submit": u"Authorship",
    u"verify": u"Approval",
    u"multi_verify": u"Approval",
    u"reject": u"Responsibility",
    u"retract": u"Responsibility",
}


def default_meaning_for(transition_id):
    """给定 transition 的建议签名含义；未知 transition 返回空串。"""
    return DEFAULT_MEANINGS.get(_as_text(transition_id).strip(), u"")


#: 新装站点的初始词表。不是强制词表 —— 现场可在控制面板按 SOP 改写。
DEFAULT_MEANING_VOCABULARY = [
    u"Approval",
    u"Review",
    u"Responsibility",
    u"Authorship",
]


def parse_meaning_vocabulary(raw_value):
    """把「一行一个」的词表文本解析成列表。

    去空行、去首尾空白、按首次出现顺序去重（顺序即下拉里的顺序，由管理员掌握）。
    解析不出任何条目时回落到默认词表，避免下拉变成空的。
    """
    items = []
    for line in _as_text(raw_value).splitlines():
        value = line.strip()
        if value and value not in items:
            items.append(value)
    return items or list(DEFAULT_MEANING_VOCABULARY)


def dumps_meaning_vocabulary(items):
    """把词表列表序列化回 registry 保存的文本。"""
    return u"\n".join(parse_meaning_vocabulary(u"\n".join(
        [_as_text(i) for i in (items or [])])))


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
        # 受控值，不是由签名人填写的自由文本。空则回落到该 transition 的建议值,
        # 这样老规则（升级前保存的、没有这个字段）也能得到一个合理的含义。
        "meaning": (
            _as_text(rule.get("meaning")).strip()
            or default_meaning_for(rule.get("transition_id"))
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
