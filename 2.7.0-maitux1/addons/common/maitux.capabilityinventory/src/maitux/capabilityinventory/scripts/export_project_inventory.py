import argparse
import io
import json
import os
from datetime import datetime
from xml.etree import ElementTree


def utc_now_iso():
    try:
        now = datetime.utcnow()
    except Exception:
        now = datetime.now()
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def localname(tag):
    if tag is None:
        return ""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def module_id_from_path(src_root, file_path):
    try:
        rel = os.path.relpath(file_path, src_root)
    except Exception:
        return "unknown"
    parts = rel.split(os.sep)
    return parts[0] if parts else "unknown"


def normalize_text(value):
    if value is None:
        return None
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except Exception:
            try:
                return value.decode("latin-1")
            except Exception:
                return str(value)
    return str(value)


def parse_xml(path):
    try:
        return ElementTree.parse(path).getroot()
    except Exception:
        return None


def xml_prop(obj, prop_name):
    if obj is None:
        return None
    for child in list(obj):
        if localname(child.tag) != "property":
            continue
        if child.get("name") != prop_name:
            continue
        elements = []
        for grand in list(child):
            if localname(grand.tag) != "element":
                continue
            val = grand.get("value")
            if val is None:
                val = grand.text
            if val is None:
                continue
            elements.append(normalize_text(val).strip())
        if elements:
            return [e for e in elements if e]
        text = child.text
        if text is None:
            return ""
        return normalize_text(text).strip()
    return None


def parse_bool(value):
    if value is None:
        return None
    v = normalize_text(value).strip().lower()
    if v in ("true", "1", "yes", "on"):
        return True
    if v in ("false", "0", "no", "off"):
        return False
    return None


def prune_none(value):
    if isinstance(value, dict):
        out_dict = {}
        for k, v in value.items():
            pv = prune_none(v)
            if pv is None:
                continue
            out_dict[k] = pv
        return out_dict
    if isinstance(value, (list, tuple, set)):
        out_list = []
        for v in value:
            pv = prune_none(v)
            if pv is None:
                continue
            out_list.append(pv)
        return out_list
    return value


def validate_inventory_or_raise(inventory, expected_scan_mode):
    if not isinstance(inventory, dict):
        raise ValueError("Inventory must be an object")
    meta = inventory.get("meta")
    if not isinstance(meta, dict):
        raise ValueError("Inventory.meta must be an object")
    if meta.get("scan_mode") != expected_scan_mode:
        raise ValueError("Inventory.meta.scan_mode mismatch")

    for key in ("generated_at", "project_id", "capability_inventory_schema_version", "phase"):
        if not meta.get(key):
            raise ValueError("Inventory.meta.%s is required" % key)

    for key in ("entities", "workflows"):
        if not isinstance(inventory.get(key), list):
            raise ValueError("Inventory.%s must be an array" % key)

    catalog = inventory.get("catalog")
    if not isinstance(catalog, dict):
        raise ValueError("Inventory.catalog must be an object")
    if not isinstance(catalog.get("indexes"), list) or not isinstance(catalog.get("metadata"), list):
        raise ValueError("Inventory.catalog.indexes/metadata must be arrays")

    security = inventory.get("security")
    if not isinstance(security, dict):
        raise ValueError("Inventory.security must be an object")
    if not isinstance(security.get("permissions"), list) or not isinstance(security.get("rolemap"), list):
        raise ValueError("Inventory.security.permissions/rolemap must be arrays")

    ui_routes = inventory.get("ui_routes")
    if not isinstance(ui_routes, dict):
        raise ValueError("Inventory.ui_routes must be an object")
    for key in ("actions", "viewlets", "views"):
        if not isinstance(ui_routes.get(key), list):
            raise ValueError("Inventory.ui_routes.%s must be an array" % key)

    for e in inventory.get("entities") or []:
        if not isinstance(e, dict) or not (e.get("type_id") or "").strip():
            raise ValueError("Entity.type_id is required")
    for w in inventory.get("workflows") or []:
        if not isinstance(w, dict) or not (w.get("workflow_id") or "").strip():
            raise ValueError("Workflow.workflow_id is required")
    for p in (security.get("permissions") or []):
        if not isinstance(p, dict) or not (p.get("id") or "").strip():
            raise ValueError("Security.permission.id is required")
    for rm in (security.get("rolemap") or []):
        if not isinstance(rm, dict) or not (rm.get("role") or "").strip():
            raise ValueError("Security.rolemap.role is required")
        perms = rm.get("permissions")
        if perms is None:
            continue
        if not isinstance(perms, list):
            raise ValueError("Security.rolemap.permissions must be an array")
    for idx in (catalog.get("indexes") or []):
        if not isinstance(idx, dict) or not (idx.get("name") or "").strip():
            raise ValueError("Catalog.index.name is required")
    for md in (catalog.get("metadata") or []):
        if not isinstance(md, dict) or not (md.get("name") or "").strip():
            raise ValueError("Catalog.metadata.name is required")
    for a in (ui_routes.get("actions") or []):
        if not isinstance(a, dict):
            raise ValueError("UI action must be an object")
        if not (a.get("id") or "").strip() or not (a.get("category") or "").strip():
            raise ValueError("UI action category/id is required")
    for v in (ui_routes.get("viewlets") or []):
        if not isinstance(v, dict) or not (v.get("name") or "").strip():
            raise ValueError("UI viewlet.name is required")
    for v in (ui_routes.get("views") or []):
        if not isinstance(v, dict) or not (v.get("name") or "").strip():
            raise ValueError("UI view.name is required")
    for capability in inventory.get("content_create_capabilities") or []:
        if not isinstance(capability, dict):
            raise ValueError("content_create_capabilities item must be an object")
        for key in (
            "content_portal_type",
            "portal_type",
            "portal_type_title",
            "framework",
            "container_type_candidates",
            "required_permission",
            "add_view_expr",
            "related_views",
            "source_refs",
        ):
            if key not in capability:
                raise ValueError("content_create_capabilities.%s is required" % key)
        if not isinstance(capability.get("container_type_candidates"), list):
            raise ValueError("content_create_capabilities.container_type_candidates must be an array")
        if not isinstance(capability.get("related_views"), list):
            raise ValueError("content_create_capabilities.related_views must be an array")
        source_refs = capability.get("source_refs")
        if not isinstance(source_refs, list) or not source_refs:
            raise ValueError("content_create_capabilities.source_refs must be a non-empty array")
        for source_ref in source_refs:
            if not isinstance(source_ref, dict) or not (source_ref.get("kind") or "").strip() or not (source_ref.get("path") or "").strip():
                raise ValueError("content_create_capabilities.source_refs entries require kind/path")
        visibility_preconditions = capability.get("visibility_preconditions")
        if visibility_preconditions is not None:
            if not isinstance(visibility_preconditions, dict):
                raise ValueError("content_create_capabilities.visibility_preconditions must be an object or null")
            for key in (
                "can_view_container",
                "can_access_container_info",
                "can_list_container_contents",
                "facts_known",
                "source_refs",
            ):
                if key not in visibility_preconditions:
                    raise ValueError("content_create_capabilities.visibility_preconditions.%s is required" % key)
            if not isinstance(visibility_preconditions.get("facts_known"), bool):
                raise ValueError("content_create_capabilities.visibility_preconditions.facts_known must be a boolean")
            visibility_sources = visibility_preconditions.get("source_refs")
            if not isinstance(visibility_sources, list) or not visibility_sources:
                raise ValueError("content_create_capabilities.visibility_preconditions.source_refs must be a non-empty array")
        for candidate in capability.get("container_type_candidates") or []:
            if not isinstance(candidate, dict):
                raise ValueError("container_type_candidates item must be an object")
            if not (candidate.get("container_type") or "").strip():
                raise ValueError("container_type_candidates.container_type is required")
            if not (candidate.get("host_container_type") or "").strip():
                raise ValueError("container_type_candidates.host_container_type is required")
            if not (candidate.get("host_object_kind") or "").strip():
                raise ValueError("container_type_candidates.host_object_kind is required")
            if not (candidate.get("reason") or "").strip():
                raise ValueError("container_type_candidates.reason is required")
            candidate_sources = candidate.get("source_refs")
            if not isinstance(candidate_sources, list) or not candidate_sources:
                raise ValueError("container_type_candidates.source_refs must be a non-empty array")


def merge_record(existing, incoming):
    if existing is None:
        return incoming
    for k, v in incoming.items():
        if k not in existing:
            existing[k] = v
            continue
        if existing[k] in (None, "", [], {}):
            if v not in (None, "", [], {}):
                existing[k] = v
                continue
        if k == "sources" and v:
            existing_sources = existing.get("sources") or []
            incoming_sources = v or []
            seen = set()
            merged = []
            for s in existing_sources + incoming_sources:
                kind = s.get("kind")
                path = s.get("path")
                key = (kind, path)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(s)
            existing["sources"] = merged
    return existing


def ensure_list(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        cleaned = []
        for v in value:
            if v is None:
                continue
            text = normalize_text(v).strip()
            if not text:
                continue
            cleaned.append(text)
        return cleaned
    text = normalize_text(value).strip()
    if not text:
        return []
    return [text]


def extract_catalog_from_catalog_xml(src_root, catalog_xml_path):
    root = parse_xml(catalog_xml_path)
    if root is None:
        return {"indexes": [], "metadata": []}
    module_id = module_id_from_path(src_root, catalog_xml_path)

    indexes_by_name = {}
    metadata_by_name = {}

    for node in root.iter():
        tag = localname(node.tag)
        if tag == "index":
            name = node.get("name")
            if not name:
                continue
            idx_type = node.get("meta_type") or node.get("type")
            record = {
                "name": name,
                "type": idx_type,
                "module_id": module_id,
                "sources": [{"kind": "gs:catalog.xml", "path": catalog_xml_path}],
            }
            indexes_by_name[name] = merge_record(indexes_by_name.get(name), record)
        if tag in ("column", "metadata", "field"):
            name = node.get("value") or node.get("name")
            if not name and node.text:
                name = normalize_text(node.text).strip()
            if not name:
                continue
            record = {
                "name": name,
                "module_id": module_id,
                "sources": [{"kind": "gs:catalog.xml", "path": catalog_xml_path}],
            }
            metadata_by_name[name] = merge_record(metadata_by_name.get(name), record)

    return {
        "indexes": [indexes_by_name[k] for k in sorted(indexes_by_name.keys())],
        "metadata": [metadata_by_name[k] for k in sorted(metadata_by_name.keys())],
    }


def extract_types_from_types_xml(src_root, types_xml_path):
    root = parse_xml(types_xml_path)
    if root is None:
        return []
    module_id = module_id_from_path(src_root, types_xml_path)
    profile_dir = os.path.dirname(types_xml_path)
    entities = []
    for obj in list(root):
        if localname(obj.tag) != "object":
            continue
        type_id = obj.get("name")
        if not type_id:
            continue
        if obj.get("meta_type") and "FTI" not in obj.get("meta_type"):
            continue
        effective_obj = obj
        effective_sources = [{"kind": "gs:types.xml", "path": types_xml_path}]
        title = xml_prop(effective_obj, "title")
        if title in (None, "") and os.path.isdir(os.path.join(profile_dir, "types")):
            candidate = os.path.join(profile_dir, "types", "%s.xml" % type_id)
            if os.path.exists(candidate):
                loaded = parse_xml(candidate)
                if loaded is not None:
                    effective_obj = loaded
                    effective_sources.append({"kind": "gs:type", "path": candidate})

        title = xml_prop(effective_obj, "title")
        klass = xml_prop(effective_obj, "klass")
        schema = xml_prop(effective_obj, "schema")
        behaviors = xml_prop(effective_obj, "behaviors")
        global_allow = parse_bool(xml_prop(effective_obj, "global_allow"))
        allowed_content_types = xml_prop(effective_obj, "allowed_content_types")
        add_view_expr = xml_prop(effective_obj, "add_view_expr")

        entities.append(
            {
                "module_id": module_id,
                "type_id": type_id,
                "title": title,
                "klass": klass,
                "behaviors": ensure_list(behaviors),
                "schema": schema,
                "add_permission": xml_prop(effective_obj, "add_permission"),
                "add_view_expr": add_view_expr,
                "global_allow": global_allow,
                "allowed_content_types": ensure_list(allowed_content_types),
                "sources": effective_sources,
            }
        )
    return entities


def dedupe_source_refs(source_refs):
    deduped = []
    seen = set()
    for source_ref in source_refs or []:
        if not isinstance(source_ref, dict):
            continue
        kind = normalize_text(source_ref.get("kind"))
        path = normalize_text(source_ref.get("path"))
        kind = kind.strip() if kind else ""
        path = path.strip() if path else ""
        if not kind or not path:
            continue
        key = (kind, path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append({"kind": kind, "path": path})
    return deduped


def build_unknown_visibility_preconditions(*source_lists):
    source_refs = []
    for source_list in source_lists:
        source_refs.extend(source_list or [])
    normalized_sources = dedupe_source_refs(source_refs)
    if not normalized_sources:
        return None
    return {
        "can_view_container": None,
        "can_access_container_info": None,
        "can_list_container_contents": None,
        "facts_known": False,
        "source_refs": normalized_sources,
    }


def related_views_from_add_view_expr(add_view_expr):
    expr = normalize_text(add_view_expr)
    if not expr:
        return []
    marker = "++add++"
    idx = expr.find(marker)
    if idx < 0:
        return []
    return [expr[idx:]]


def ensure_content_create_capability_required_keys(capability):
    if not isinstance(capability, dict):
        return capability
    normalized = dict(capability)
    if "content_portal_type" not in normalized:
        normalized["content_portal_type"] = normalized.get("portal_type")
    if "required_permission" not in normalized:
        normalized["required_permission"] = None
    if "add_view_expr" not in normalized:
        normalized["add_view_expr"] = None
    return normalized


def ensure_container_candidate_required_keys(candidate):
    if not isinstance(candidate, dict):
        return candidate
    normalized = dict(candidate)
    if "host_container_type" not in normalized:
        normalized["host_container_type"] = normalized.get("container_type")
    if "host_object_kind" not in normalized:
        normalized["host_object_kind"] = "folderish_portal_type"
    return normalized


def build_content_create_capabilities(entities):
    capabilities = []
    entities_by_id = {}
    for entity in entities or []:
        if not isinstance(entity, dict):
            continue
        type_id = normalize_text(entity.get("type_id"))
        if not type_id:
            continue
        entities_by_id[type_id.strip()] = entity

    for type_id in sorted(entities_by_id.keys()):
        entity = entities_by_id[type_id]
        entity_sources = dedupe_source_refs(entity.get("sources") or [])
        if not entity_sources:
            continue

        container_candidates = []
        for container_type_id in sorted(entities_by_id.keys()):
            container_entity = entities_by_id[container_type_id]
            allowed_content_types = ensure_list(container_entity.get("allowed_content_types"))
            if type_id not in allowed_content_types:
                continue
            candidate_sources = dedupe_source_refs(container_entity.get("sources") or [])
            if not candidate_sources:
                continue
            container_candidates.append(
                ensure_container_candidate_required_keys(
                    {
                        "container_type": container_type_id,
                        "host_container_type": container_type_id,
                        "host_object_kind": "folderish_portal_type",
                        "reason": "allowed_content_types contains %s" % type_id,
                        "source_refs": candidate_sources,
                    }
                )
            )

        add_view_expr = entity.get("add_view_expr")
        visibility_preconditions = build_unknown_visibility_preconditions(
            entity_sources,
            [
                source_ref
                for container_candidate in container_candidates
                for source_ref in list((container_candidate or {}).get("source_refs") or [])
            ],
        )
        capability = ensure_content_create_capability_required_keys(
            {
                "content_portal_type": type_id,
                "portal_type": type_id,
                "portal_type_title": entity.get("title") or type_id,
                "framework": entity.get("framework") or "unknown",
                "container_type_candidates": container_candidates,
                "required_permission": entity.get("add_permission"),
                "add_view_expr": add_view_expr,
                "related_views": related_views_from_add_view_expr(add_view_expr),
                "visibility_preconditions": visibility_preconditions,
                "source_refs": entity_sources,
            }
        )
        capabilities.append(capability)
    return capabilities


def extract_workflows_from_workflows_xml(src_root, workflows_xml_path):
    root = parse_xml(workflows_xml_path)
    if root is None:
        return []
    module_id = module_id_from_path(src_root, workflows_xml_path)
    profile_dir = os.path.dirname(workflows_xml_path)

    workflow_ids = []
    bindings = {}
    for child in list(root):
        tag = localname(child.tag)
        if tag == "object":
            wf_id = child.get("name")
            if wf_id:
                workflow_ids.append(wf_id)
        if tag == "bindings":
            for type_node in list(child):
                if localname(type_node.tag) != "type":
                    continue
                type_id = type_node.get("type_id")
                for bound in list(type_node):
                    if localname(bound.tag) != "bound-workflow":
                        continue
                    wf_id = bound.get("workflow_id")
                    if not wf_id or not type_id:
                        continue
                    bindings.setdefault(wf_id, set()).add(type_id)

    workflows = []
    for wf_id in sorted(set(workflow_ids)):
        definition_path = os.path.join(profile_dir, "workflows", wf_id, "definition.xml")
        title = None
        states = []
        transitions = []
        from_by_transition = {}

        definition_root = parse_xml(definition_path) if os.path.exists(definition_path) else None
        if definition_root is not None:
            title = definition_root.get("title") or definition_root.get("name")

            for state in definition_root.findall(".//state"):
                sid = state.get("state_id") or state.get("id")
                if not sid:
                    continue
                states.append({"id": sid, "title": state.get("title")})
                for exit_t in state.findall("./exit-transition"):
                    tid = exit_t.get("transition_id") or exit_t.get("id")
                    if not tid:
                        continue
                    from_by_transition.setdefault(tid, []).append(sid)

            for t in definition_root.findall(".//transition"):
                tid = t.get("transition_id") or t.get("id")
                if not tid:
                    continue
                permission = None
                guard = t.find("./guard")
                if guard is not None:
                    gp = guard.find("./guard-permission")
                    if gp is not None and gp.text:
                        permission = normalize_text(gp.text).strip()
                transitions.append(
                    {
                        "id": tid,
                        "title": t.get("title"),
                        "from": sorted(set(from_by_transition.get(tid, []))),
                        "to": t.get("new_state") or t.get("new_state_id"),
                        "permission": permission,
                    }
                )

        workflows.append(
            {
                "module_id": module_id,
                "workflow_id": wf_id,
                "title": title,
                "states": states,
                "transitions": transitions,
                "bound_types": sorted(bindings.get(wf_id, set())),
                "sources": (
                    [{"kind": "gs:workflows.xml", "path": workflows_xml_path}]
                    + (
                        [{"kind": "gs:workflow:definition.xml", "path": definition_path}]
                        if os.path.exists(definition_path)
                        else []
                    )
                ),
            }
        )
    return workflows


def extract_security_from_rolemap(src_root, rolemap_path):
    root = parse_xml(rolemap_path)
    if root is None:
        return {"permissions": [], "rolemap": []}
    module_id = module_id_from_path(src_root, rolemap_path)

    permissions = []
    role_to_permissions = {}
    for perm in root.findall(".//permission"):
        perm_id = perm.get("name") or perm.get("id")
        if not perm_id:
            continue
        permissions.append(
            {
                "id": perm_id,
                "title": perm_id,
                "module_id": module_id,
                "sources": [{"kind": "gs:rolemap.xml", "path": rolemap_path}],
            }
        )
        for role in perm.findall("./role"):
            role_name = role.get("name") or (normalize_text(role.text).strip() if role.text else None)
            if not role_name:
                continue
            role_to_permissions.setdefault(role_name, set()).add(perm_id)

    rolemap = []
    for role, perms in sorted(role_to_permissions.items()):
        rolemap.append(
            {
                "role": role,
                "permissions": sorted(perms),
                "module_id": module_id,
                "sources": [{"kind": "gs:rolemap.xml", "path": rolemap_path}],
            }
        )
    return {"permissions": permissions, "rolemap": rolemap}


def extract_actions_from_actions_xml(src_root, actions_xml_path):
    root = parse_xml(actions_xml_path)
    if root is None:
        return []
    module_id = module_id_from_path(src_root, actions_xml_path)

    actions = []
    for category in root.findall("./object"):
        if localname(category.tag) != "object":
            continue
        category_id = category.get("name")
        if not category_id:
            continue
        for action in category.findall("./object"):
            if localname(action.tag) != "object":
                continue
            action_id = action.get("name")
            if not action_id:
                continue
            permissions = xml_prop(action, "permissions")
            permission = permissions[0] if isinstance(permissions, list) and permissions else None
            actions.append(
                {
                    "module_id": module_id,
                    "id": action_id,
                    "category": category_id,
                    "title": xml_prop(action, "title"),
                    "url_expr": xml_prop(action, "url_expr"),
                    "permission": permission,
                    "sources": [{"kind": "gs:actions.xml", "path": actions_xml_path}],
                }
            )
    return actions


def extract_viewlet_orders_from_viewlets_xml(src_root, viewlets_xml_path):
    root = parse_xml(viewlets_xml_path)
    if root is None:
        return []
    module_id = module_id_from_path(src_root, viewlets_xml_path)

    results = []
    for order in root.findall(".//order"):
        manager = order.get("manager")
        for viewlet in order.findall("./viewlet"):
            name = viewlet.get("name")
            if not name:
                continue
            results.append(
                {
                    "module_id": module_id,
                    "name": name,
                    "manager": manager,
                    "permission": None,
                    "class": None,
                    "template": None,
                    "for": None,
                    "sources": [{"kind": "gs:viewlets.xml", "path": viewlets_xml_path}],
                }
            )
    return results


def extract_ui_from_zcml(src_root, zcml_path):
    root = parse_xml(zcml_path)
    if root is None:
        return {"permissions": [], "views": [], "viewlets": []}
    module_id = module_id_from_path(src_root, zcml_path)

    permissions = []
    views = []
    viewlets = []

    for node in root.iter():
        tag = localname(node.tag)
        if tag == "permission":
            pid = node.get("id")
            if pid:
                permissions.append(
                    {
                        "id": pid,
                        "title": node.get("title") or pid,
                        "module_id": module_id,
                        "sources": [{"kind": "zcml:permission", "path": zcml_path}],
                    }
                )
        if tag in ("page", "view"):
            name = node.get("name")
            if not name:
                continue
            views.append(
                {
                    "module_id": module_id,
                    "name": name,
                    "for": node.get("for"),
                    "class": node.get("class"),
                    "permission": node.get("permission"),
                    "template": node.get("template"),
                    "sources": [{"kind": "zcml:browser:%s" % tag, "path": zcml_path}],
                }
            )
        if tag == "viewlet":
            name = node.get("name")
            if not name:
                continue
            viewlets.append(
                {
                    "module_id": module_id,
                    "name": name,
                    "manager": node.get("manager"),
                    "for": node.get("for"),
                    "class": node.get("class"),
                    "permission": node.get("permission"),
                    "template": node.get("template"),
                    "sources": [{"kind": "zcml:browser:viewlet", "path": zcml_path}],
                }
            )

    return {"permissions": permissions, "views": views, "viewlets": viewlets}


def resolve_output_path(output_dir_or_file):
    lowered = (
        output_dir_or_file.lower()
        if hasattr(output_dir_or_file, "lower")
        else str(output_dir_or_file).lower()
    )
    if lowered.endswith(".json"):
        return output_dir_or_file
    return os.path.join(output_dir_or_file, "capability_inventory.project.json")


def iter_profile_files(src_root):
    for root_dir, dirs, files in os.walk(src_root):
        base = os.path.basename(root_dir)
        if base != "profiles":
            continue
        for profile_name in dirs:
            profile_dir = os.path.join(root_dir, profile_name)
            for fn in ("types.xml", "workflows.xml", "rolemap.xml", "actions.xml", "viewlets.xml", "catalog.xml"):
                p = os.path.join(profile_dir, fn)
                if os.path.exists(p):
                    yield p


def iter_zcml_files(addon_root):
    for root_dir, dirs, files in os.walk(addon_root):
        for fn in files:
            if fn == "configure.zcml":
                yield os.path.join(root_dir, fn)


def export_project_inventory(src_root, project_id, schema_version, phase, output_path):
    entities_by_id = {}
    workflows_by_id = {}
    actions_by_id = {}
    viewlets_by_name = {}
    views_by_name = {}
    permissions_by_id = {}
    rolemap_by_role = {}
    catalog_indexes_by_name = {}
    catalog_metadata_by_name = {}

    for file_path in iter_profile_files(src_root):
        base = os.path.basename(file_path)
        if base == "types.xml":
            for e in extract_types_from_types_xml(src_root, file_path):
                entities_by_id[e["type_id"]] = merge_record(entities_by_id.get(e["type_id"]), e)
        elif base == "workflows.xml":
            for wf in extract_workflows_from_workflows_xml(src_root, file_path):
                workflows_by_id[wf["workflow_id"]] = merge_record(workflows_by_id.get(wf["workflow_id"]), wf)
        elif base == "rolemap.xml":
            sec = extract_security_from_rolemap(src_root, file_path)
            for p in sec["permissions"]:
                permissions_by_id[p["id"]] = merge_record(permissions_by_id.get(p["id"]), p)
            for rm in sec["rolemap"]:
                rolemap_by_role[rm["role"]] = merge_record(rolemap_by_role.get(rm["role"]), rm)
        elif base == "actions.xml":
            for a in extract_actions_from_actions_xml(src_root, file_path):
                key = "%s/%s" % (a.get("category"), a.get("id"))
                actions_by_id[key] = merge_record(actions_by_id.get(key), a)
        elif base == "viewlets.xml":
            for v in extract_viewlet_orders_from_viewlets_xml(src_root, file_path):
                viewlets_by_name[v["name"]] = merge_record(viewlets_by_name.get(v["name"]), v)
        elif base == "catalog.xml":
            cat = extract_catalog_from_catalog_xml(src_root, file_path)
            for idx in cat.get("indexes") or []:
                catalog_indexes_by_name[idx["name"]] = merge_record(catalog_indexes_by_name.get(idx["name"]), idx)
            for md in cat.get("metadata") or []:
                catalog_metadata_by_name[md["name"]] = merge_record(catalog_metadata_by_name.get(md["name"]), md)

    for addon in [os.path.join(src_root, name) for name in os.listdir(src_root)]:
        if not os.path.isdir(addon):
            continue
        for zcml_path in iter_zcml_files(addon):
            ui = extract_ui_from_zcml(src_root, zcml_path)
            for p in ui["permissions"]:
                permissions_by_id[p["id"]] = merge_record(permissions_by_id.get(p["id"]), p)
            for v in ui["views"]:
                views_by_name[v["name"]] = merge_record(views_by_name.get(v["name"]), v)
            for v in ui["viewlets"]:
                viewlets_by_name[v["name"]] = merge_record(viewlets_by_name.get(v["name"]), v)

    content_create_capabilities = build_content_create_capabilities(
        [entities_by_id[k] for k in sorted(entities_by_id.keys())]
    )

    inventory = {
        "meta": {
            "generated_at": utc_now_iso(),
            "project_id": project_id,
            "plone_version": None,
            "senaite_version": None,
            "capability_inventory_schema_version": schema_version,
            "scan_mode": "project",
            "phase": phase,
            "source_paths": [src_root],
        },
        "entities": [entities_by_id[k] for k in sorted(entities_by_id.keys())],
        "content_create_capabilities": content_create_capabilities,
        "workflows": [workflows_by_id[k] for k in sorted(workflows_by_id.keys())],
        "catalog": {
            "indexes": [catalog_indexes_by_name[k] for k in sorted(catalog_indexes_by_name.keys())],
            "metadata": [catalog_metadata_by_name[k] for k in sorted(catalog_metadata_by_name.keys())],
        },
        "security": {
            "permissions": [permissions_by_id[k] for k in sorted(permissions_by_id.keys())],
            "rolemap": [rolemap_by_role[k] for k in sorted(rolemap_by_role.keys())],
            "policy_placeholders": [],
        },
        "ui_routes": {
            "actions": [actions_by_id[k] for k in sorted(actions_by_id.keys())],
            "viewlets": [viewlets_by_name[k] for k in sorted(viewlets_by_name.keys())],
            "views": [views_by_name[k] for k in sorted(views_by_name.keys())],
        },
    }

    inventory = prune_none(inventory)
    inventory["content_create_capabilities"] = content_create_capabilities
    out_dir = os.path.dirname(output_path)
    if out_dir and not os.path.isdir(out_dir):
        try:
            os.makedirs(out_dir)
        except Exception:
            pass

    validate_inventory_or_raise(inventory, "project")

    with io.open(output_path, "w", encoding="utf-8") as f:
        payload = json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True)
        f.write(payload)

    return output_path


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--src-root", dest="src_root", required=True)
    parser.add_argument("--out", dest="out", required=True)
    parser.add_argument("--project-id", dest="project_id", default="Maitux")
    parser.add_argument("--schema-version", dest="schema_version", default="0.1")
    parser.add_argument("--phase", dest="phase", default="phase1")
    args = parser.parse_args(argv)

    output_path = resolve_output_path(args.out)
    src_root = os.path.abspath(args.src_root)
    return export_project_inventory(src_root, args.project_id, args.schema_version, args.phase, output_path)


if __name__ == "__main__":
    import sys

    main(sys.argv[1:])


