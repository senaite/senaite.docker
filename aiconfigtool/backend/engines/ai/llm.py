"""LLM 需求解析引擎。

解析策略：
1. 先用关键词和规则判断每一条需求的 changeType。
2. 仅在规则无法可靠判断时，再调用 AI 做 changeType 分类。
3. 已判定 changeType 后，按类型使用专用提示词和专用结构化输出。
4. 当前只正式实现 AddField / UpdatePermission，UpdateListing 仅预留接口。
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Optional

from engines.ai.deterministic import (
    _build_field_description,
    _extract_field_title,
    _extract_object_name,
    _is_explicit_type_alias,
    _normalize_field_name,
    _resolve_type_candidates,
    _resolve_known_type_by_alias,
    _split_requirements,
    _type_aliases,
)
from shared import errors
from shared.result import Result

_SUPPORTED_PROVIDERS = {"ollama", "cloud"}
_ADD_FIELD_ALIASES = {"addfield", "add_field", "add field"}
_UPDATE_PERMISSION_ALIASES = {
    "updatepermission",
    "update_permission",
    "update permission",
    "grantpermission",
    "grant_permission",
    "grant permission",
}
_UPDATE_LISTING_ALIASES = {"updatelisting", "update_listing", "update listing"}
_ADD_FIELD_ALIAS_KEYS = {
    re.sub(r"[^a-z]", "", item) for item in _ADD_FIELD_ALIASES
}
_UPDATE_PERMISSION_ALIAS_KEYS = {
    re.sub(r"[^a-z]", "", item) for item in _UPDATE_PERMISSION_ALIASES
}
_UPDATE_LISTING_ALIAS_KEYS = {
    re.sub(r"[^a-z]", "", item) for item in _UPDATE_LISTING_ALIASES
}
_FIELD_TYPE_ALIASES = {
    "stringfield": "StringField",
    "string": "StringField",
    "textline": "StringField",
    "textfield": "TextField",
    "text": "TextField",
    "textarea": "TextField",
    "integerfield": "IntegerField",
    "integer": "IntegerField",
    "int": "IntegerField",
    "floatfield": "FloatField",
    "float": "FloatField",
    "number": "FloatField",
    "booleanfield": "BooleanField",
    "boolean": "BooleanField",
    "bool": "BooleanField",
    "datefield": "DateField",
    "date": "DateField",
    "datetimefield": "DateTimeField",
    "datetime": "DateTimeField",
}
_FIELD_KEYWORDS = (
    "字段",
    "field",
    "属性",
    "textline",
    "textarea",
    "stringfield",
    "textfield",
    "integerfield",
    "floatfield",
    "booleanfield",
    "datefield",
    "datetimefield",
)
_LISTING_KEYWORDS = ("列表", "列表页", "列表视图", "listing", "list view", "列显示", "显示该字段")
_PERMISSION_KEYWORDS = (
    "权限",
    "角色",
    "role",
    "授权",
    "撤权",
    "撤销",
    "grant",
    "revoke",
    "allow",
    "deny",
)
_PERMISSION_GRANT_KEYWORDS = (
    "grant",
    "授权",
    "赋权",
    "赋予",
    "允许",
    "增加权限",
    "添加权限",
    "加权限",
    "新增权限",
)
_PERMISSION_REVOKE_KEYWORDS = (
    "revoke",
    "撤权",
    "撤销",
    "撤消",
    "移除权限",
    "减少权限",
    "去掉权限",
    "取消权限",
    "禁止",
    "deny",
)
_SEGMENT_LIMIT = 20


def _config_path() -> str:
    workspace = os.environ.get("AICONFIG_WORKSPACE")
    if workspace:
        return os.path.join(os.path.abspath(workspace), "config.json")
    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(backend_dir, "..", "data", "config.json")


def _read_ai_config() -> dict:
    path = _config_path()
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
            return data.get("ai") or {}
    return {}


def _extract_json_text(text: str) -> Optional[str]:
    raw = (text or "").strip()
    if not raw:
        return None

    fenced = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", raw, re.IGNORECASE)
    if fenced:
        raw = fenced.group(1).strip()

    if raw[:1] in "[{":
        return raw

    starts = [idx for idx in (raw.find("{"), raw.find("[")) if idx >= 0]
    if not starts:
        return None
    start = min(starts)
    candidate = raw[start:].strip()
    for end_char in ("}", "]"):
        end = candidate.rfind(end_char)
        if end > 0:
            return candidate[: end + 1]
    return None


def _safe_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "y", "required", "mandatory"}


def _normalize_change_type(value: str) -> str:
    key = re.sub(r"[^a-z]", "", str(value or "").lower())
    if key in _ADD_FIELD_ALIAS_KEYS:
        return "AddField"
    if key in _UPDATE_PERMISSION_ALIAS_KEYS:
        return "UpdatePermission"
    if key in _UPDATE_LISTING_ALIAS_KEYS:
        return "UpdateListing"
    return str(value or "").strip()


def _normalize_field_type(value: str) -> str:
    key = re.sub(r"[\s_]", "", str(value or "").strip().lower())
    return _FIELD_TYPE_ALIASES.get(key, "StringField")


def _normalize_permission_action(value: str) -> str:
    key = re.sub(r"[^a-z]", "", str(value or "").strip().lower())
    if key in {"grant", "add", "allow", "assign", "create"}:
        return "grant"
    if key in {"revoke", "remove", "deny", "unassign"}:
        return "revoke"
    return ""


def _safe_text(value) -> str:
    if isinstance(value, list):
        for item in value:
            text = str(item or "").strip()
            if text:
                return text
        return ""
    return str(value or "").strip()


def _has_any_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    lowered = (text or "").lower()
    return any(word in text or word in lowered for word in keywords)


def _build_types_context(inventory_summary: Optional[dict]) -> list[dict]:
    types = []
    for type_id, meta in sorted(((inventory_summary or {}).get("types") or {}).items()):
        fields = [
            f.get("name")
            for f in (meta.get("fields") or [])
            if isinstance(f, dict) and f.get("name")
        ][:20]
        types.append(
            {
                "typeId": type_id,
                "title": meta.get("title") or "",
                "framework": meta.get("framework") or "unknown",
                "addPermission": meta.get("addPermission") or "",
                "aliases": sorted(_type_aliases(type_id, meta)),
                "knownFields": fields,
            }
        )
    return types


def _build_type_options(inventory_summary: Optional[dict], allowed_type_ids=None) -> list[dict]:
    allowed = set(allowed_type_ids or [])
    options = []
    for item in _build_types_context(inventory_summary):
        if allowed and item["typeId"] not in allowed:
            continue
        options.append(item)
    return options


def _detect_permission_operation(text: str) -> Optional[str]:
    lowered = (text or "").lower()
    grant = _has_any_keyword(text, _PERMISSION_GRANT_KEYWORDS) or (
        ("增加" in text or "添加" in text or "新增" in text or "add" in lowered)
        and ("权限" in text or "permission" in lowered)
    )
    revoke = _has_any_keyword(text, _PERMISSION_REVOKE_KEYWORDS)
    if grant and revoke:
        return None
    if grant:
        return "grant"
    if revoke:
        return "revoke"
    return None


def _detect_change_type_by_keywords(text: str) -> Optional[str]:
    has_listing = _has_any_keyword(text, _LISTING_KEYWORDS)
    has_field = _has_any_keyword(text, _FIELD_KEYWORDS)
    permission_action = _detect_permission_operation(text)
    has_permission = permission_action is not None or _has_any_keyword(text, _PERMISSION_KEYWORDS)

    if has_listing:
        return "UpdateListing"
    if has_permission and not has_field:
        return "UpdatePermission"
    if has_field and not has_permission:
        return "AddField"
    return None


def _build_change_type_prompt(natural_language: str, inventory_summary: Optional[dict]) -> str:
    return (
        "你是 changeType 分类器。"
        "请根据用户需求只判断变更类型，不要做多余推理，不要输出解释。\n"
        "只输出一个 JSON 对象，格式必须是：{\"changeType\":\"AddField|UpdatePermission|UpdateListing|Unknown\"}\n"
        "判断规则：\n"
        "1. 新增字段、字段类型、必填/可选 -> AddField\n"
        "2. 给角色增加/减少/撤销/授予权限 -> UpdatePermission\n"
        "3. 列表页列显示调整 -> UpdateListing\n"
        "4. 不确定时输出 Unknown\n\n"
        "已知内容类型：\n%s\n\n"
        "用户需求：\n%s\n"
        % (
            json.dumps(_build_types_context(inventory_summary), ensure_ascii=False, indent=2),
            natural_language,
        )
    )


def _build_add_field_prompt(
    natural_language: str,
    inventory_summary: Optional[dict],
    type_options=None,
    locked_type_id: str = "",
) -> str:
    options = _build_type_options(inventory_summary, type_options)
    options_text = json.dumps(options, ensure_ascii=False, indent=2)
    if locked_type_id:
        type_rule = (
            "1. targetType 已由规则锁定，typeId 必须固定输出为 \"%s\"，不允许改写。\n"
            % locked_type_id
        )
    else:
        type_rule = (
            "1. typeId 只能从下面给出的 SENAITE 对象候选列表中选择一个，不允许自创、不允许输出候选外的值。\n"
        )
    return (
        "你是 AddField 结构化提取器。\n"
        "背景：你正在处理 SENAITE 系统中的对象字段需求。\n"
        "目标：把一条“新增字段”需求解析成严格 JSON，不要输出解释、Markdown、注释。\n"
        "只输出一个 JSON 对象，字段必须严格为：\n"
        "{\n"
        "  \"typeId\": \"\",\n"
        "  \"fieldName\": \"\",\n"
        "  \"fieldTitle\": \"\",\n"
        "  \"fieldDescription\": \"\",\n"
        "  \"fieldType\": \"StringField|TextField|IntegerField|FloatField|BooleanField|DateField|DateTimeField\",\n"
        "  \"required\": false,\n"
        "  \"description\": \"\"\n"
        "}\n"
        "规则：\n"
        "%s"
        "2. fieldName 必须转成稳定的英文/下划线标识，如 sample_code、client_level。\n"
        "3. fieldTitle 填用户界面显示标题，优先保留用户原始写法，如“地域”“Company”。\n"
        "4. fieldDescription 填字段说明，简洁、自然，不要写技术实现信息。\n"
        "5. fieldType 只能从给定枚举中选一个。\n"
        "6. required 只输出 true 或 false。\n"
        "7. 如果原句包含列表页/列表视图/显示列等意思，不要输出 UpdateListing，只保留 AddField 本身。\n\n"
        "SENAITE 对象候选（已去重）：\n%s\n\n"
        "用户需求：\n%s\n"
        % (
            type_rule,
            options_text,
            natural_language,
        )
    )


def _build_update_permission_prompt(
    natural_language: str,
    inventory_summary: Optional[dict],
    type_options=None,
    locked_type_id: str = "",
) -> str:
    options = _build_type_options(inventory_summary, type_options)
    options_text = json.dumps(options, ensure_ascii=False, indent=2)
    if locked_type_id:
        type_rule = (
            "2. 若本句涉及对象权限，targetType 已由规则锁定，必须固定输出为 \"%s\"；若不是对象权限则留空。\n"
            % locked_type_id
        )
    else:
        type_rule = (
            "2. 若本句涉及对象权限，targetType 只能从下面给出的 SENAITE 对象候选列表中选择一个；若不是对象权限可留空。\n"
        )
    return (
        "你是 UpdatePermission 结构化提取器。\n"
        "背景：你正在处理 SENAITE 系统中的对象权限需求。\n"
        "目标：把一条“角色权限变更”需求解析成严格 JSON，不要输出解释、Markdown、注释。\n"
        "只输出一个 JSON 对象，字段必须严格为：\n"
        "{\n"
        "  \"roleName\": \"\",\n"
        "  \"targetType\": \"\",\n"
        "  \"permissionAction\": \"grant|revoke\",\n"
        "  \"permissionId\": \"\",\n"
        "  \"description\": \"\"\n"
        "}\n"
        "规则：\n"
        "1. permissionAction 只能是 grant 或 revoke。\n"
        "%s"
        "3. 如果是“给某角色添加/减少创建某类型的权限”，targetType 填 typeId，permissionId 留空。\n"
        "4. 如果用户明确说了具体权限 ID/权限名，可填 permissionId；若未明确则保持空字符串。\n"
        "5. roleName 只填角色标识，不带“角色”二字。\n\n"
        "SENAITE 对象候选（已去重）：\n%s\n\n"
        "用户需求：\n%s\n"
        % (
            type_rule,
            options_text,
            natural_language,
        )
    )


def _build_update_listing_prompt(natural_language: str, inventory_summary: Optional[dict]) -> str:
    return (
        "你是 UpdateListing 结构化提取器。当前该能力仅预留接口，暂不使用。\n"
        "已知内容类型：\n%s\n\n"
        "用户需求：\n%s\n"
        % (
            json.dumps(_build_types_context(inventory_summary), ensure_ascii=False, indent=2),
            natural_language,
        )
    )


def _extract_payload_dict(payload) -> Optional[dict]:
    if isinstance(payload, dict):
        if isinstance(payload.get("change"), dict):
            return payload.get("change")
        return payload
    return None


def _family_for_change_type(change_type: str) -> str:
    if change_type == "UpdatePermission":
        return "permission"
    return "field"


def _normalize_add_field_payload(
    payload,
    known_types: dict,
    allowed_type_ids=None,
    locked_type_id: str = "",
    segment: str = "",
) -> Result:
    item = _extract_payload_dict(payload)
    if not item:
        return Result.failure("AddField 结构化结果为空", code=errors.CHANGE_SPEC_INVALID)

    raw_type_id = _safe_text(item.get("typeId") or item.get("targetType"))
    if locked_type_id:
        type_id = locked_type_id
    else:
        type_id = raw_type_id if raw_type_id in known_types else _resolve_known_type_by_alias(raw_type_id, known_types)
    if not type_id or type_id not in known_types:
        return Result.failure(
            "AI 识别的 AddField 目标类型无效：%s" % (raw_type_id or "empty"),
            code=errors.CHANGE_SPEC_INVALID,
        )
    allowed = list(allowed_type_ids or [])
    if allowed and type_id not in allowed:
        return Result.failure(
            "AI 识别的 AddField 目标类型不在允许候选内：%s" % (raw_type_id or type_id),
            code=errors.CHANGE_SPEC_INVALID,
        )

    field_name = _normalize_field_name(item.get("fieldName") or item.get("name") or "")
    if not field_name:
        return Result.failure("AI 没有产出有效字段名", code=errors.CHANGE_SPEC_INVALID)
    type_title = (known_types.get(type_id) or {}).get("title") or type_id
    field_title = (
        _safe_text(item.get("fieldTitle") or item.get("title"))
        or _extract_field_title(segment)
        or field_name
    )
    field_description = (
        _safe_text(item.get("fieldDescription") or item.get("helpText") or item.get("uiDescription"))
        or _build_field_description(type_title, field_title, field_name)
    )

    return Result.success(
        {
            "changeType": "AddField",
            "description": _safe_text(item.get("description")) or ("为 %s 添加字段 %s" % (type_id, field_name)),
            "typeId": type_id,
            "typeTitle": type_title,
            "fieldName": field_name,
            "fieldTitle": field_title,
            "fieldDescription": field_description,
            "fieldType": _normalize_field_type(item.get("fieldType")),
            "required": _safe_bool(item.get("required")),
            "framework": (known_types.get(type_id) or {}).get("framework", "unknown"),
        }
    )


def _normalize_update_permission_payload(
    payload,
    known_types: dict,
    allowed_type_ids=None,
    locked_type_id: str = "",
) -> Result:
    item = _extract_payload_dict(payload)
    if not item:
        return Result.failure("UpdatePermission 结构化结果为空", code=errors.CHANGE_SPEC_INVALID)

    role_name = _safe_text(item.get("roleName") or item.get("role"))
    raw_target_type = _safe_text(item.get("targetType") or item.get("typeId"))
    if locked_type_id and raw_target_type:
        target_type = locked_type_id
    else:
        target_type = raw_target_type if raw_target_type in known_types else _resolve_known_type_by_alias(raw_target_type, known_types)
    permission_id = _safe_text(item.get("permissionId") or item.get("permission"))
    permission_action = _normalize_permission_action(
        item.get("permissionAction") or item.get("operation")
    )

    if not role_name:
        return Result.failure("AI 没有产出有效角色名", code=errors.CHANGE_SPEC_INVALID)
    if not permission_action:
        return Result.failure("AI 没有产出有效权限动作 grant/revoke", code=errors.CHANGE_SPEC_INVALID)
    if raw_target_type and target_type and target_type not in known_types:
        return Result.failure(
            "AI 识别的权限目标类型无效：%s" % raw_target_type,
            code=errors.CHANGE_SPEC_INVALID,
        )
    if raw_target_type and not target_type and not permission_id:
        return Result.failure(
            "AI 识别的权限目标类型无效：%s" % raw_target_type,
            code=errors.CHANGE_SPEC_INVALID,
        )
    allowed = list(allowed_type_ids or [])
    if target_type and allowed and target_type not in allowed:
        return Result.failure(
            "AI 识别的权限目标类型不在允许候选内：%s" % (raw_target_type or target_type),
            code=errors.CHANGE_SPEC_INVALID,
        )
    if not target_type and not permission_id:
        return Result.failure(
            "UpdatePermission 至少需要 targetType 或 permissionId 之一",
            code=errors.CHANGE_SPEC_INVALID,
        )

    description = _safe_text(item.get("description"))
    if not description:
        verb = "添加" if permission_action == "grant" else "移除"
        if target_type:
            description = "给 %s 角色%s %s 的权限" % (role_name, verb, target_type)
        else:
            description = "给 %s 角色%s %s 权限" % (role_name, verb, permission_id)

    change = {
        "changeType": "UpdatePermission",
        "description": description,
        "roleName": role_name,
        "permissionAction": permission_action,
    }
    if target_type:
        change["targetType"] = target_type
        change["targetTitle"] = (known_types.get(target_type) or {}).get("title") or target_type
    if permission_id:
        change["permissionId"] = permission_id
    return Result.success(change)


class LLMRequirementEngine:
    def __init__(self, provider: Optional[str] = None, ai_config: Optional[dict] = None) -> None:
        self._ai_config = ai_config or _read_ai_config()
        self.provider = _safe_text(provider or self._ai_config.get("provider")).lower()

    def is_available(self) -> bool:
        if self.provider not in _SUPPORTED_PROVIDERS:
            return False
        if self.provider == "ollama":
            ollama = self._ai_config.get("ollama") or {}
            return bool(_safe_text(ollama.get("baseUrl")) and _safe_text(ollama.get("model")))
        cloud = self._ai_config.get("cloud") or {}
        return bool(_safe_text(cloud.get("baseUrl")) and _safe_text(cloud.get("model")))

    def parse_to_change_spec(
        self,
        natural_language: str,
        site_code: str,
        inventory_ref: str,
        inventory_summary: Optional[dict] = None,
    ) -> Result:
        if self.provider not in _SUPPORTED_PROVIDERS:
            return Result.failure(
                "当前 AI provider 不可用: %s" % (self.provider or "empty"),
                code=errors.CHANGE_SPEC_INVALID,
            )
        if not self.is_available():
            return Result.failure(
                "AI 配置不完整，无法调用 %s" % self.provider,
                code=errors.CHANGE_SPEC_INVALID,
            )

        text = _safe_text(natural_language)
        if not text:
            return Result.failure("需求描述为空", code=errors.CHANGE_SPEC_INVALID)

        segments = [seg for seg in _split_requirements(text) if _safe_text(seg)]
        if len(segments) > _SEGMENT_LIMIT:
            return Result.failure(
                "需求条数过多，当前最多支持 %d 条" % _SEGMENT_LIMIT,
                code=errors.CHANGE_SPEC_INVALID,
            )

        known_types = (inventory_summary or {}).get("types") or {}
        changes = []
        families = set()

        for idx, segment in enumerate(segments, start=1):
            route = self._route_change_type(segment, inventory_summary)
            if route.is_failure():
                err = route.error
                return Result.failure(
                    "第 %d 条需求无法判断变更类型：%s" % (idx, err.message),
                    code=err.code,
                    suggestion=err.suggestion,
                    details={"segment": segment},
                )
            change_type = route.value
            if change_type == "UpdateListing":
                return Result.failure(
                    "第 %d 条需求属于 UpdateListing，但该能力当前仅预留接口，尚未实现" % idx,
                    code=errors.CHANGE_SPEC_INVALID,
                    suggestion="请先只提交 AddField 或 UpdatePermission 需求",
                    details={"segment": segment},
                )

            parsed = self._parse_segment(segment, change_type, inventory_summary)
            if parsed.is_failure():
                err = parsed.error
                return Result.failure(
                    "第 %d 条需求解析失败：%s" % (idx, err.message),
                    code=err.code,
                    suggestion=err.suggestion,
                    details={"segment": segment, "changeType": change_type},
                )

            changes.append(parsed.value)
            families.add(_family_for_change_type(change_type))

        if not changes:
            return Result.failure("AI 没有解析出任何变更项", code=errors.CHANGE_SPEC_INVALID)
        if len(families) > 1:
            return Result.failure(
                "同一个 Addon 不能同时包含字段和权限变更",
                code=errors.CHANGE_SPEC_INVALID,
            )

        return Result.success(
            {
                "version": "1.0",
                "siteCode": site_code,
                "inventoryRef": inventory_ref,
                "changes": changes,
                "risks": [
                    {
                        "level": "low",
                        "message": "本次 change_spec 由 %s 解析生成，生成前仍会经过 Gate1/Gate2 校验"
                        % self.provider,
                    }
                ],
            }
        )

    def _request(self, prompt: str) -> Result:
        try:
            if self.provider == "ollama":
                return self._request_ollama(prompt)
            return self._request_cloud(prompt)
        except urllib.error.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                body = ""
            return Result.failure(
                "%s 调用失败：HTTP %s %s" % (self.provider, exc.code, body),
                code=errors.CHANGE_SPEC_INVALID,
            )
        except Exception as exc:
            return Result.failure(
                "%s 调用失败：%s" % (self.provider, str(exc)),
                code=errors.CHANGE_SPEC_INVALID,
            )

    def _request_ollama(self, prompt: str) -> Result:
        ollama = self._ai_config.get("ollama") or {}
        url = (_safe_text(ollama.get("baseUrl")) or "http://127.0.0.1:11434").rstrip("/") + "/api/generate"
        payload = json.dumps(
            {
                "model": _safe_text(ollama.get("model")),
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.1},
            }
        ).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        return Result.success(data.get("response", ""))

    def _request_cloud(self, prompt: str) -> Result:
        cloud = self._ai_config.get("cloud") or {}
        url = _safe_text(cloud.get("baseUrl")).rstrip("/") + "/chat/completions"
        payload = json.dumps(
            {
                "model": _safe_text(cloud.get("model")),
                "messages": [
                    {"role": "system", "content": "你只输出 JSON，不输出任何解释。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 1200,
            }
        ).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer " + _safe_text(cloud.get("apiKey")))
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        text = ""
        try:
            text = data["choices"][0]["message"]["content"]
        except Exception:
            text = ""
        return Result.success(text)

    def _parse_response(self, text: str) -> Result:
        json_text = _extract_json_text(text)
        if not json_text:
            return Result.failure("AI 没有返回可解析的 JSON", code=errors.CHANGE_SPEC_INVALID)
        try:
            payload = json.loads(json_text)
        except Exception as exc:
            return Result.failure(
                "AI 返回的 JSON 无法解析：%s" % str(exc),
                code=errors.CHANGE_SPEC_INVALID,
            )
        return Result.success(payload)

    def _route_change_type(self, segment: str, inventory_summary: Optional[dict]) -> Result:
        change_type = _detect_change_type_by_keywords(segment)
        if change_type:
            return Result.success(change_type)

        prompt = _build_change_type_prompt(segment, inventory_summary)
        raw = self._request(prompt)
        if raw.is_failure():
            return raw
        parsed = self._parse_response(raw.value or "")
        if parsed.is_failure():
            return parsed

        payload = _extract_payload_dict(parsed.value)
        change_type = _normalize_change_type((payload or {}).get("changeType"))
        if change_type in {"AddField", "UpdatePermission", "UpdateListing"}:
            return Result.success(change_type)
        return Result.failure(
            "AI 未能可靠判断 changeType",
            code=errors.CHANGE_SPEC_INVALID,
            suggestion="请在需求中明确写出“字段”或“权限”等关键词",
        )

    def _parse_segment(self, segment: str, change_type: str, inventory_summary: Optional[dict]) -> Result:
        known_types = ((inventory_summary or {}).get("types") or {})
        object_name = _extract_object_name(segment)
        type_candidates = _resolve_type_candidates(segment, known_types)
        if object_name and _is_explicit_type_alias(object_name) and not type_candidates:
            return Result.failure(
                "当前摸底对象中找不到与“%s”对应的 SENAITE 对象候选" % object_name.strip(),
                code=errors.CHANGE_SPEC_INVALID,
                suggestion="请检查摸底文件是否缺少对应对象，或改用更精确的对象名",
            )
        locked_type_id = type_candidates[0] if len(type_candidates) == 1 else ""
        type_options = type_candidates or list(known_types.keys())

        if change_type == "AddField":
            prompt = _build_add_field_prompt(
                segment,
                inventory_summary,
                type_options=type_options,
                locked_type_id=locked_type_id,
            )
        elif change_type == "UpdatePermission":
            prompt = _build_update_permission_prompt(
                segment,
                inventory_summary,
                type_options=type_options,
                locked_type_id=locked_type_id,
            )
        elif change_type == "UpdateListing":
            prompt = _build_update_listing_prompt(segment, inventory_summary)
        else:
            return Result.failure(
                "当前不支持的 changeType: %s" % change_type,
                code=errors.CHANGE_SPEC_INVALID,
            )

        raw = self._request(prompt)
        if raw.is_failure():
            return raw
        parsed = self._parse_response(raw.value or "")
        if parsed.is_failure():
            return parsed

        if change_type == "AddField":
            return _normalize_add_field_payload(
                parsed.value,
                known_types,
                allowed_type_ids=type_options,
                locked_type_id=locked_type_id,
                segment=segment,
            )
        if change_type == "UpdatePermission":
            return _normalize_update_permission_payload(
                parsed.value,
                known_types,
                allowed_type_ids=type_options,
                locked_type_id=locked_type_id,
            )
        return Result.failure(
            "UpdateListing 当前仅预留接口，尚未实现",
            code=errors.CHANGE_SPEC_INVALID,
        )
