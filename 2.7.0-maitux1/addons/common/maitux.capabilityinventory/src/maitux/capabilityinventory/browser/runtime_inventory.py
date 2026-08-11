# -*- coding: utf-8 -*-

import imp
import json
import os

from Products.CMFCore.utils import getToolByName
from Products.Five.browser import BrowserView


def _dedupe_source_refs(source_refs):
    deduped = []
    seen = set()
    for source_ref in source_refs or []:
        if not isinstance(source_ref, dict):
            continue
        kind = str(source_ref.get("kind") or "").strip()
        path = str(source_ref.get("path") or "").strip()
        if not kind or not path:
            continue
        key = (kind, path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append({"kind": kind, "path": path})
    return deduped


def _normalize_content_create_capabilities(capabilities):
    normalized = []
    for capability in capabilities or []:
        if not isinstance(capability, dict):
            normalized.append(capability)
            continue
        item = dict(capability)
        if "content_portal_type" not in item:
            item["content_portal_type"] = item.get("portal_type")
        if "required_permission" not in item:
            item["required_permission"] = None
        if "add_view_expr" not in item:
            item["add_view_expr"] = None
        container_candidates = []
        for candidate in item.get("container_type_candidates") or []:
            if not isinstance(candidate, dict):
                container_candidates.append(candidate)
                continue
            candidate_item = dict(candidate)
            if "host_container_type" not in candidate_item:
                candidate_item["host_container_type"] = candidate_item.get("container_type")
            if "host_object_kind" not in candidate_item:
                candidate_item["host_object_kind"] = "folderish_portal_type"
            container_candidates.append(candidate_item)
        item["container_type_candidates"] = container_candidates
        if "visibility_preconditions" not in item:
            source_refs = list(item.get("source_refs") or [])
            for candidate_item in container_candidates:
                if not isinstance(candidate_item, dict):
                    continue
                source_refs.extend(list(candidate_item.get("source_refs") or []))
            item["visibility_preconditions"] = {
                "can_view_container": None,
                "can_access_container_info": None,
                "can_list_container_contents": None,
                "facts_known": False,
                "source_refs": _dedupe_source_refs(source_refs),
            }
        normalized.append(item)
    return normalized


class MaituxRuntimeInventoryExportView(BrowserView):
    def __call__(self):
        self.request.response.setHeader("Content-Type", "application/json; charset=utf-8")
        self.request.response.setHeader("Cache-Control", "no-store")

        portal = self.context
        if getattr(portal, "portal_catalog", None) is None:
            try:
                portal = getToolByName(self.context, "portal_url").getPortalObject()
            except Exception:
                portal = self.context
        try:
            from zope.component.hooks import setSite

            setSite(portal)
        except Exception:
            pass

        project_id = self.request.form.get("project_id") or "Maitux"
        schema_version = self.request.form.get("schema_version") or "0.1"
        phase = self.request.form.get("phase") or "phase1"

        try:
            from maitux.capabilityinventory.scripts import export_runtime_inventory as runtime_export
        except Exception:
            host_src_root = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..")
            )
            script_path = os.path.join(
                host_src_root,
                "maitux.capabilityinventory",
                "src",
                "maitux",
                "capabilityinventory",
                "scripts",
                "export_runtime_inventory.py",
            )
            runtime_export = imp.load_source("maitux_capabilityinventory_export_runtime_inventory", script_path)

        inventory = runtime_export.build_inventory(portal, project_id, schema_version, phase)
        inventory["meta"]["plone_version"] = runtime_export.safe_dist_version("Plone")
        inventory["meta"]["senaite_version"] = runtime_export.safe_dist_version("senaite.core")
        inventory["content_create_capabilities"] = _normalize_content_create_capabilities(
            inventory.get("content_create_capabilities") or []
        )
        runtime_export.validate_inventory_or_raise(inventory, "runtime")
        inventory = runtime_export.normalize_for_json(inventory)
        content_create_capabilities = inventory.get("content_create_capabilities") or []
        inventory = runtime_export.prune_none(inventory)
        inventory["content_create_capabilities"] = content_create_capabilities
        return json.dumps(inventory, ensure_ascii=False, indent=2, sort_keys=True)

