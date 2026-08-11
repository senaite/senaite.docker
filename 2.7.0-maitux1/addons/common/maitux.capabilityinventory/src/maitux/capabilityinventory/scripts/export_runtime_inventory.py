import argparse
import io
import importlib
import json
import os
from datetime import datetime

from Products.CMFCore.utils import getToolByName

try:
    text_type = unicode
    binary_type = str
except NameError:
    text_type = str
    binary_type = bytes


def _decode_binary(value):
    try:
        return value.decode("utf-8")
    except Exception:
        return value.decode("latin-1", errors="replace")


def to_unicode(value):
    if value is None:
        return None
    if isinstance(value, text_type):
        return value
    if isinstance(value, binary_type):
        return _decode_binary(value)
    try:
        return text_type(value)
    except Exception:
        try:
            rendered = repr(value)
        except Exception:
            rendered = "<unprintable %s>" % getattr(getattr(value, "__class__", None), "__name__", "object")
        if isinstance(rendered, text_type):
            return rendered
        if isinstance(rendered, binary_type):
            return _decode_binary(rendered)
        return text_type(rendered)


def normalize_for_json(value):
    if isinstance(value, dict):
        normalized = {}
        for k, v in value.items():
            normalized[to_unicode(k)] = normalize_for_json(v)
        return normalized
    if isinstance(value, (list, tuple, set)):
        return [normalize_for_json(v) for v in value]
    if isinstance(value, (bool, int, float)):
        return value
    return to_unicode(value)


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


def utc_now_iso():
    try:
        now = datetime.utcnow()
    except Exception:
        now = datetime.now()
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def safe_dist_version(dist_name):
    try:
        from pkg_resources import get_distribution

        return get_distribution(dist_name).version
    except Exception:
        return None


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

    if expected_scan_mode == "runtime":
        entities = inventory.get("entities") or []
        if not isinstance(entities, list):
            raise ValueError("Inventory.entities must be an array")
        for e in entities:
            if not isinstance(e, dict):
                continue
            mt = e.get("meta_type")
            mt_str = (to_unicode(mt) or "").strip()
            if not mt_str:
                raise ValueError("Runtime entity.meta_type is required (type_id=%s)" % (e.get("type_id") or "unknown"))
            fw = e.get("framework")
            if fw not in ("dexterity", "archetypes", "unknown"):
                raise ValueError("Runtime entity.framework invalid (type_id=%s)" % (e.get("type_id") or "unknown"))
            if not isinstance(e.get("dexterity_fields"), list):
                raise ValueError("Runtime entity.dexterity_fields must be an array (type_id=%s)" % (e.get("type_id") or "unknown"))
            if not isinstance(e.get("at_fields"), list):
                raise ValueError("Runtime entity.at_fields must be an array (type_id=%s)" % (e.get("type_id") or "unknown"))
            if fw == "unknown":
                reason = e.get("framework_reason") or e.get("notes")
                reason_str = (to_unicode(reason) or "").strip()
                if not reason_str:
                    raise ValueError("Runtime entity.framework_reason is required when framework=unknown (type_id=%s)" % (e.get("type_id") or "unknown"))

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
        if not isinstance(e, dict) or not (to_unicode(e.get("type_id")) or "").strip():
            raise ValueError("Entity.type_id is required")
    for w in inventory.get("workflows") or []:
        if not isinstance(w, dict) or not (to_unicode(w.get("workflow_id")) or "").strip():
            raise ValueError("Workflow.workflow_id is required")
    for p in (security.get("permissions") or []):
        if not isinstance(p, dict) or not (to_unicode(p.get("id")) or "").strip():
            raise ValueError("Security.permission.id is required")
    for rm in (security.get("rolemap") or []):
        if not isinstance(rm, dict) or not (to_unicode(rm.get("role")) or "").strip():
            raise ValueError("Security.rolemap.role is required")
        perms = rm.get("permissions")
        if perms is None:
            continue
        if not isinstance(perms, list):
            raise ValueError("Security.rolemap.permissions must be an array")
    for idx in (catalog.get("indexes") or []):
        if not isinstance(idx, dict) or not (to_unicode(idx.get("name")) or "").strip():
            raise ValueError("Catalog.index.name is required")
    for md in (catalog.get("metadata") or []):
        if not isinstance(md, dict) or not (to_unicode(md.get("name")) or "").strip():
            raise ValueError("Catalog.metadata.name is required")
    for a in (ui_routes.get("actions") or []):
        if not isinstance(a, dict):
            raise ValueError("UI action must be an object")
        if not (to_unicode(a.get("id")) or "").strip() or not (to_unicode(a.get("category")) or "").strip():
            raise ValueError("UI action category/id is required")
    for v in (ui_routes.get("viewlets") or []):
        if not isinstance(v, dict) or not (to_unicode(v.get("name")) or "").strip():
            raise ValueError("UI viewlet.name is required")
    for v in (ui_routes.get("views") or []):
        if not isinstance(v, dict) or not (to_unicode(v.get("name")) or "").strip():
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
            kind = (to_unicode(source_ref.get("kind")) or "").strip() if isinstance(source_ref, dict) else ""
            path = (to_unicode(source_ref.get("path")) or "").strip() if isinstance(source_ref, dict) else ""
            if not kind or not path:
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
            if not (to_unicode(candidate.get("container_type")) or "").strip():
                raise ValueError("container_type_candidates.container_type is required")
            if not (to_unicode(candidate.get("host_container_type")) or "").strip():
                raise ValueError("container_type_candidates.host_container_type is required")
            if not (to_unicode(candidate.get("host_object_kind")) or "").strip():
                raise ValueError("container_type_candidates.host_object_kind is required")
            if not (to_unicode(candidate.get("reason")) or "").strip():
                raise ValueError("container_type_candidates.reason is required")
            candidate_sources = candidate.get("source_refs")
            if not isinstance(candidate_sources, list) or not candidate_sources:
                raise ValueError("container_type_candidates.source_refs must be a non-empty array")


def infer_module_id_from_dotted(value):
    text = to_unicode(value) if value is not None else None
    if not text:
        return None
    parts = [p for p in text.split(".") if p]
    if not parts:
        return None
    if len(parts) >= 2 and parts[0] in ("senaite", "maitux"):
        return "%s.%s" % (parts[0], parts[1])
    return parts[0]


def infer_module_id_from_permission(permission):
    p = to_unicode(permission) if permission is not None else None
    if not p:
        return None
    if ":" not in p:
        return None
    prefix = p.split(":", 1)[0].strip()
    if not prefix:
        return None
    if prefix.startswith("senaite.") or prefix.startswith("maitux."):
        parts = [x for x in prefix.split(".") if x]
        if len(parts) >= 2:
            return "%s.%s" % (parts[0], parts[1])
        return prefix
    return prefix


def infer_module_id_from_workflow_id(wf_id):
    wid = to_unicode(wf_id) if wf_id is not None else None
    if not wid:
        return None
    lowered = wid.lower()
    if lowered.startswith("senaite_storage"):
        return "senaite.storage"
    if lowered.startswith("senaite_databox"):
        return "senaite.databox"
    if lowered.startswith("senaite_health"):
        return "senaite.health"
    if lowered.startswith("senaite_"):
        return "senaite.core"
    if lowered.startswith("maitux_"):
        parts = [p for p in lowered.split("_") if p]
        if len(parts) >= 2:
            return "maitux.%s" % parts[1]
        return "maitux"
    return None


def pick_site(app, site_id=None):
    if site_id:
        try:
            return app._getOb(site_id)
        except Exception:
            pass
    candidates = []
    try:
        candidates = list(app.objectIds())
    except Exception:
        candidates = []
    for preferred in ("senaite", "Plone"):
        if preferred in candidates:
            try:
                obj = app._getOb(preferred)
                if getattr(obj, "portal_catalog", None) is not None:
                    return obj
            except Exception:
                pass
    for oid in candidates:
        try:
            obj = app._getOb(oid)
        except Exception:
            continue
        if getattr(obj, "portal_catalog", None) is not None:
            return obj
    raise KeyError("No Plone site found")


def safe_list(value):
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _safe_json_scalar(value):
    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return to_unicode(value)
    if callable(value):
        return None
    return to_unicode(value)


def _infer_framework(fti, meta_type, klass):
    mt = (to_unicode(meta_type) or "").strip()
    kl = (to_unicode(klass) or "").strip()
    try:
        from plone.dexterity.interfaces import IDexterityFTI

        if IDexterityFTI.providedBy(fti):
            return "dexterity", "IDexterityFTI"
    except Exception:
        pass
    lowered = mt.lower()
    if "dexterity" in lowered:
        return "dexterity", "meta_type=%s" % mt
    if "archetypes" in lowered:
        return "archetypes", "meta_type=%s" % mt
    if "factory" in lowered and kl:
        if "archetypes" in kl.lower() or ".content." in kl.lower():
            return "archetypes", "meta_type=%s klass=%s" % (mt, kl)
    return "unknown", "no_match meta_type=%s klass=%s" % (mt or "?", kl or "?")


def _iter_schema_fields(schema_iface):
    out = [{"name": "", "type": "", "required": False, "default": None}][:0]
    if schema_iface is None:
        return out
    try:
        from zope.schema import getFieldsInOrder

        pairs = getFieldsInOrder(schema_iface)
    except Exception:
        pairs = []
    for name, field in pairs:
        if not name:
            continue
        out.append(
            {
                "name": to_unicode(name),
                "type": getattr(field, "__class__", type(field)).__name__,
                "required": bool(getattr(field, "required", False)),
                "default": _safe_json_scalar(getattr(field, "default", None)),
            }
        )
    return out


def _resolve_dotted(dotted):
    s = (to_unicode(dotted) or "").strip()
    if not s or "." not in s:
        return None
    module_name, attr = s.rsplit(".", 1)
    try:
        module = importlib.import_module(module_name)
        return getattr(module, attr, None)
    except Exception:
        return None


def _extract_dexterity_fields_from_fti(fti):
    fields = []
    schema_iface = None
    try:
        schema_iface = fti.lookupSchema()
    except Exception:
        schema_iface = None
    fields.extend(_iter_schema_fields(schema_iface))

    behaviors = safe_list(getattr(fti, "behaviors", None))
    for dotted in behaviors:
        iface = _resolve_dotted(dotted)
        fields.extend(_iter_schema_fields(iface))

    seen = set()
    out = []
    for f in fields:
        name = f.get("name")
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(f)
    return out


def _extract_at_fields_from_object(obj):
    if obj is None:
        return []
    schema = None
    try:
        schema = obj.Schema()
    except Exception:
        schema = None
    if schema is None:
        try:
            schema = getattr(obj, "schema", None)
        except Exception:
            schema = None
    if schema is None:
        return []
    try:
        fields = list(schema.fields())
    except Exception:
        fields = []
    out = []
    for f in fields:
        try:
            name = f.getName()
        except Exception:
            name = getattr(f, "name", None)
        if not name:
            continue
        out.append(
            {
                "name": to_unicode(name),
                "type": getattr(f, "__class__", type(f)).__name__,
                "required": bool(getattr(f, "required", False)),
                "default": _safe_json_scalar(getattr(f, "default", None)),
            }
        )
    seen = set()
    uniq = []
    for it in out:
        n = it.get("name")
        if not n or n in seen:
            continue
        seen.add(n)
        uniq.append(it)
    return uniq


def _extract_at_fields_from_schemaextenders(type_id):
    if not type_id:
        return []
    try:
        from Products.Archetypes.interfaces import IBaseObject
        from archetypes.schemaextender.interfaces import ISchemaExtender
        from zope.component import getAdapters
        from zope.interface import alsoProvides
    except Exception:
        return []

    class _Dummy(object):
        portal_type = None

    dummy = _Dummy()
    dummy.portal_type = type_id
    try:
        alsoProvides(dummy, IBaseObject)
    except Exception:
        pass

    out = []
    try:
        adapters = list(getAdapters((dummy,), ISchemaExtender))
    except Exception:
        adapters = []
    for _, adapter in adapters:
        try:
            fields = adapter.getFields() or []
        except Exception:
            continue
        for f in fields:
            if f is None:
                continue
            try:
                name = f.getName()
            except Exception:
                name = getattr(f, "name", None)
            if not name:
                continue
            out.append(
                {
                    "name": to_unicode(name),
                    "type": getattr(f, "__class__", type(f)).__name__,
                    "required": bool(getattr(f, "required", False)),
                    "default": _safe_json_scalar(getattr(f, "default", None)),
                }
            )
    seen = set()
    uniq = []
    for it in out:
        n = it.get("name")
        if not n or n in seen:
            continue
        seen.add(n)
        uniq.append(it)
    return uniq


def _sample_object_for_type(site, type_id):
    try:
        catalog = getToolByName(site, "portal_catalog")
    except Exception:
        catalog = None
    if catalog is None:
        return None
    try:
        brains = catalog(portal_type=type_id)[:1]
    except Exception:
        brains = []
    if not brains:
        return None
    try:
        return brains[0].getObject()
    except Exception:
        return None


def dedupe_source_refs(source_refs):
    deduped = []
    seen = set()
    for source_ref in source_refs or []:
        if not isinstance(source_ref, dict):
            continue
        kind = (to_unicode(source_ref.get("kind")) or "").strip()
        path = (to_unicode(source_ref.get("path")) or "").strip()
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
    expr = (to_unicode(add_view_expr) or "").strip()
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
        type_id = (to_unicode(entity.get("type_id")) or "").strip()
        if not type_id:
            continue
        entities_by_id[type_id] = entity

    for type_id in sorted(entities_by_id.keys()):
        entity = entities_by_id[type_id]
        entity_sources = dedupe_source_refs(entity.get("sources") or [])
        if not entity_sources:
            continue

        container_candidates = []
        for container_type_id in sorted(entities_by_id.keys()):
            container_entity = entities_by_id[container_type_id]
            allowed_content_types = safe_list(container_entity.get("allowed_content_types"))
            allowed_content_types = [(to_unicode(v) or "").strip() for v in allowed_content_types if (to_unicode(v) or "").strip()]
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
        capabilities.append(
            ensure_content_create_capability_required_keys(
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
        )
    return capabilities


def extract_portal_types(site):
    portal_types = getToolByName(site, "portal_types")
    entities = []
    type_ids = []
    try:
        type_ids = list(portal_types.objectIds())
    except Exception:
        type_ids = []
    for type_id in sorted(type_ids):
        try:
            fti = portal_types.getTypeInfo(type_id)
        except Exception:
            fti = None
        if fti is None:
            continue

        behaviors = getattr(fti, "behaviors", None)
        allowed_content_types = getattr(fti, "allowed_content_types", None)
        meta_type = getattr(fti, "meta_type", None) or getattr(fti, "__class__", type(fti)).__name__
        meta_type_str = (to_unicode(meta_type) or "").strip() or "unknown"
        framework, framework_reason = _infer_framework(fti, meta_type_str, getattr(fti, "klass", None))

        if framework == "unknown":
            klass_obj = _resolve_dotted(getattr(fti, "klass", None))
            if klass_obj is not None and (hasattr(klass_obj, "Schema") or hasattr(klass_obj, "schema")):
                framework = "archetypes"
                framework_reason = "klass_has_schema %s" % (to_unicode(getattr(fti, "klass", None)) or "?")
            else:
                try:
                    schema_iface = fti.lookupSchema()
                except Exception:
                    schema_iface = None
                if schema_iface is not None:
                    framework = "dexterity"
                    framework_reason = "fti_lookupSchema"
                else:
                    sample = _sample_object_for_type(site, type_id)
                    if sample is not None and (hasattr(sample, "Schema") or hasattr(sample, "schema")):
                        framework = "archetypes"
                        framework_reason = "sample_object_has_schema"
                    else:
                        extender_fields = _extract_at_fields_from_schemaextenders(type_id)
                        if extender_fields:
                            framework = "archetypes"
                            framework_reason = "schemaextender_adapters"

        dexterity_fields = []
        at_fields = []
        if framework == "dexterity":
            dexterity_fields = _extract_dexterity_fields_from_fti(fti)
        elif framework == "archetypes":
            sample = _sample_object_for_type(site, type_id)
            at_fields = _extract_at_fields_from_object(sample)
            if not at_fields:
                klass_obj = _resolve_dotted(getattr(fti, "klass", None))
                if klass_obj is not None:
                    try:
                        at_fields = _extract_at_fields_from_object(klass_obj)
                    except Exception:
                        at_fields = []
            if not at_fields:
                at_fields = _extract_at_fields_from_schemaextenders(type_id)

        entity = {
            "module_id": "runtime/unknown",
            "type_id": type_id,
            "title": getattr(fti, "title", None),
            "meta_type": meta_type_str,
            "framework": framework,
            "framework_reason": framework_reason,
            "klass": getattr(fti, "klass", None),
            "behaviors": safe_list(behaviors),
            "schema": None,
            "dexterity_fields": dexterity_fields,
            "at_fields": at_fields,
            "add_permission": getattr(fti, "add_permission", None),
            "add_view_expr": getattr(fti, "add_view_expr", None),
            "global_allow": getattr(fti, "global_allow", None),
            "allowed_content_types": safe_list(allowed_content_types),
            "sources": [{"kind": "runtime:portal_types", "path": "portal_types/%s" % type_id}],
        }
        inferred = infer_module_id_from_dotted(entity.get("klass"))
        if inferred:
            entity["module_id"] = inferred
        entities.append(entity)
    return entities


def extract_workflows(site, type_ids):
    portal_workflow = getToolByName(site, "portal_workflow")

    wf_ids = []
    try:
        wf_ids = list(portal_workflow.objectIds())
    except Exception:
        wf_ids = []

    bound_types_by_wf = {"__seed__": set([""])}
    bound_types_by_wf.pop("__seed__", None)
    for type_id in type_ids:
        try:
            chain = portal_workflow.getChainForPortalType(type_id) or []
        except Exception:
            chain = []
        for wf_id in chain:
            bound_types_by_wf.setdefault(wf_id, set()).add(type_id)

    workflows = []
    for wf_id in sorted(wf_ids):
        wf = None
        try:
            wf = portal_workflow.getWorkflowById(wf_id)
        except Exception:
            wf = None
        if wf is None:
            continue

        states = []
        transitions = []

        wf_states = getattr(wf, "states", None)
        if wf_states is not None:
            try:
                state_ids = list(wf_states.objectIds())
            except Exception:
                state_ids = []
            for state_id in state_ids:
                try:
                    state = wf_states.get(state_id)
                except Exception:
                    state = None
                states.append({"id": state_id, "title": getattr(state, "title", None)})

        transition_from = {"__seed__": [""][:0]}
        transition_from.pop("__seed__", None)
        if wf_states is not None:
            for state_row in states:
                state_id = state_row.get("id")
                if not state_id:
                    continue
                try:
                    state = wf_states.get(state_id)
                except Exception:
                    state = None
                if state is None:
                    continue
                outgoing = safe_list(getattr(state, "transitions", None))
                for tid in outgoing:
                    if not tid:
                        continue
                    transition_from.setdefault(str(tid), []).append(str(state_id))

        wf_transitions = getattr(wf, "transitions", None)
        if wf_transitions is not None:
            transition_ids = []
            try:
                transition_ids = list(wf_transitions.objectIds())
            except Exception:
                try:
                    transition_ids = list(wf_transitions.keys())
                except Exception:
                    transition_ids = []

            for tid in transition_ids:
                try:
                    transition = wf_transitions.get(tid)
                except Exception:
                    try:
                        transition = wf_transitions[tid]
                    except Exception:
                        transition = None

                guard = getattr(transition, "guard", None)
                guard_permissions = safe_list(getattr(guard, "permissions", None))
                permission = guard_permissions[0] if guard_permissions else None

                transitions.append(
                    {
                        "id": tid,
                        "title": getattr(transition, "title", None),
                        "from": transition_from.get(tid, []),
                        "to": getattr(transition, "new_state_id", None),
                        "permission": permission,
                    }
                )

        workflows.append(
            {
                "module_id": infer_module_id_from_workflow_id(wf_id) or "runtime/unknown",
                "workflow_id": wf_id,
                "title": getattr(wf, "title", None),
                "states": states,
                "transitions": transitions,
                "bound_types": sorted(bound_types_by_wf.get(wf_id, set())),
                "sources": [{"kind": "runtime:portal_workflow", "path": "portal_workflow"}],
            }
        )

    return workflows


def extract_catalog(site):
    portal_catalog = getToolByName(site, "portal_catalog")

    indexes = []
    index_names = []
    try:
        index_names = list(portal_catalog.indexes())
    except Exception:
        try:
            index_names = list(portal_catalog._catalog.indexes.keys())
        except Exception:
            index_names = []

    for name in sorted(index_names):
        idx_type = None
        try:
            idx = portal_catalog._catalog.getIndex(name)
            idx_type = getattr(idx, "meta_type", None) or idx.__class__.__name__
        except Exception:
            idx_type = None
        indexes.append({"name": name, "type": idx_type, "module_id": "runtime/unknown"})

    metadata = []
    metadata_names = []
    try:
        metadata_names = list(portal_catalog.schema())
    except Exception:
        metadata_names = []
    for name in sorted(metadata_names):
        metadata.append({"name": name, "module_id": "runtime/unknown"})

    return {"indexes": indexes, "metadata": metadata}


def extract_security(site):
    permission_names = []
    try:
        inherited = site.ac_inherited_permissions(1) or []
        permission_names = [p[0] for p in inherited if p and p[0]]
    except Exception:
        permission_names = []

    permissions = []
    for name in sorted(set(permission_names)):
        permissions.append({"id": name, "title": name, "module_id": infer_module_id_from_permission(name) or "runtime/unknown"})

    role_to_permissions = {"__seed__": set([""])}
    role_to_permissions.pop("__seed__", None)
    for perm in permissions:
        perm_name = perm["id"]
        roles_info = [{}, ""][:0]
        try:
            roles_info = site.rolesOfPermission(perm_name) or []
        except Exception:
            roles_info = []
        for entry in roles_info:
            role_name = None
            selected = True
            if isinstance(entry, dict):
                role_name = entry.get("name")
                selected = bool(entry.get("selected"))
            else:
                role_name = entry
            role_name = to_unicode(role_name)
            if not role_name or not selected:
                continue
            role_to_permissions.setdefault(role_name, set()).add(perm_name)

    rolemap = [
        {"role": role, "permissions": sorted(perms), "module_id": "runtime/unknown"}
        for role, perms in sorted(role_to_permissions.items())
    ]

    policy_placeholders = [
        "Permission policy deferred; Phase 1 exports minimal role-permission mapping."
    ]

    return {"permissions": permissions, "rolemap": rolemap, "policy_placeholders": policy_placeholders}


def extract_actions(site):
    portal_actions = None
    try:
        portal_actions = getToolByName(site, "portal_actions")
    except Exception:
        portal_actions = None
    if portal_actions is None:
        return []

    actions = []
    category_ids = []
    try:
        category_ids = list(portal_actions.objectIds())
    except Exception:
        category_ids = []

    for category in sorted(category_ids):
        try:
            container = portal_actions._getOb(category)
        except Exception:
            continue
        try:
            items = list(container.objectValues())
        except Exception:
            items = []
        for action in items:
            action_id = getattr(action, "id", None) or getattr(action, "getId", lambda: None)()
            permissions = getattr(action, "permissions", None)
            permission = None
            if isinstance(permissions, (list, tuple)) and permissions:
                permission = permissions[0]
            url_expr = None
            try:
                url_expr = getattr(action, "action", None)
            except Exception:
                url_expr = None
            actions.append(
                {
                    "module_id": infer_module_id_from_permission(permission) or "runtime/unknown",
                    "id": action_id,
                    "category": category,
                    "title": getattr(action, "title", None),
                    "url_expr": str(url_expr) if url_expr is not None else None,
                    "permission": permission,
                    "sources": [{"kind": "runtime:portal_actions", "path": "portal_actions"}],
                }
            )

    return actions


def build_inventory(site, project_id, schema_version, phase):
    entities = extract_portal_types(site)
    type_ids = [e["type_id"] for e in entities]
    workflows = extract_workflows(site, type_ids)
    catalog = extract_catalog(site)
    security = extract_security(site)
    actions = extract_actions(site)
    content_create_capabilities = build_content_create_capabilities(entities)

    inventory = {
        "meta": {
            "generated_at": utc_now_iso(),
            "project_id": project_id,
            "plone_version": None,
            "senaite_version": None,
            "capability_inventory_schema_version": schema_version,
            "scan_mode": "runtime",
            "phase": phase,
            "source_paths": [],
        },
        "entities": entities,
        "content_create_capabilities": content_create_capabilities,
        "workflows": workflows,
        "catalog": catalog,
        "security": security,
        "ui_routes": {"actions": actions, "viewlets": [], "views": []},
    }
    return inventory


def resolve_output_path(output_dir_or_file):
    lowered = (
        output_dir_or_file.lower()
        if hasattr(output_dir_or_file, "lower")
        else str(output_dir_or_file).lower()
    )
    if lowered.endswith(".json"):
        return output_dir_or_file
    return os.path.join(output_dir_or_file, "capability_inventory.runtime.json")


def main(app, argv):
    if argv and argv[0] == "-c":
        argv = argv[2:]
    elif argv and str(argv[0]).endswith(".py"):
        argv = argv[1:]

    parser = argparse.ArgumentParser()
    parser.add_argument("--site", dest="site_id", default=None)
    parser.add_argument("--out", dest="out", required=True)
    parser.add_argument("--project-id", dest="project_id", default="Maitux")
    parser.add_argument("--schema-version", dest="schema_version", default="0.1")
    parser.add_argument("--phase", dest="phase", default="phase1")
    args = parser.parse_args(argv)

    site = pick_site(app, args.site_id)
    try:
        from zope.component.hooks import setSite

        setSite(site)
    except Exception:
        pass
    output_path = resolve_output_path(args.out)
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.isdir(output_dir):
        try:
            os.makedirs(output_dir)
        except Exception:
            pass

    inventory = build_inventory(site, args.project_id, args.schema_version, args.phase)
    inventory["meta"]["plone_version"] = safe_dist_version("Plone")
    inventory["meta"]["senaite_version"] = safe_dist_version("senaite.core")
    validate_inventory_or_raise(inventory, "runtime")

    with io.open(output_path, "w", encoding="utf-8") as f:
        inventory = normalize_for_json(inventory)
        content_create_capabilities = inventory.get("content_create_capabilities") or []
        inventory = prune_none(inventory)
        inventory["content_create_capabilities"] = content_create_capabilities
        payload = json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True)
        f.write(payload)
    return output_path


try:
    app_obj = globals().get("app")
except Exception:
    app_obj = None

if app_obj is not None:
    try:
        from Testing.makerequest import makerequest

        app_obj = makerequest(app_obj)
    except Exception:
        pass

    try:
        import sys

        argv = sys.argv[1:]
    except Exception:
        argv = []
    main(app_obj, argv)

