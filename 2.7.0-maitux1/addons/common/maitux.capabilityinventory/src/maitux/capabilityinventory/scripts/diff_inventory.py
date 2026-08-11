import argparse
import io
import json
import os
from datetime import datetime


def utc_now_iso():
    try:
        now = datetime.utcnow()
    except Exception:
        now = datetime.now()
    return now.strftime("%Y-%m-%dT%H:%M:%SZ")


def local_today_cn():
    now = datetime.now()
    try:
        return u"%d年%d月%d日" % (now.year, now.month, now.day)
    except Exception:
        return "%d-%02d-%02d" % (now.year, now.month, now.day)


def to_text(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except Exception:
            return value.decode("latin-1", errors="replace")
    return str(value)



def load_json(path):
    with io.open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    out_dir = os.path.dirname(path)
    if out_dir and not os.path.isdir(out_dir):
        try:
            os.makedirs(out_dir)
        except Exception:
            pass
    with io.open(path, "w", encoding="utf-8") as f:
        payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True)
        f.write(payload)

def read_existing_creation_time(md_path):
    if not md_path or not os.path.exists(md_path):
        return None
    try:
        with io.open(md_path, "r", encoding="utf-8") as f:
            head = []
            for _ in range(30):
                line = f.readline()
                if not line:
                    break
                head.append(line.strip())
    except Exception:
        return None
    for line in head:
        if line.startswith("文档创建时间："):
            return line.split("：", 1)[1].strip()
    return None


def write_markdown(md_path, markdown_text):
    out_dir = os.path.dirname(md_path)
    if out_dir and not os.path.isdir(out_dir):
        try:
            os.makedirs(out_dir)
        except Exception:
            pass
    with io.open(md_path, "w", encoding="utf-8") as f:
        if not isinstance(markdown_text, type(u"")):
            markdown_text = to_text(markdown_text)
        f.write(markdown_text)


def find_default_schema_path():
    try:
        here = os.path.dirname(os.path.abspath(__file__))
    except Exception:
        here = os.getcwd()
    relative = os.path.join("docs", "AiConfigTool", "能力摸底", "capability_inventory.schema.json")
    cur = here
    for _ in range(12):
        candidate = os.path.join(cur, relative)
        if os.path.exists(candidate):
            return candidate
        parent = os.path.dirname(cur)
        if not parent or parent == cur:
            break
        cur = parent
    return None


def validate_inventory_with_schema(inventory, schema, expected_scan_mode, label):
    if not isinstance(inventory, dict):
        raise ValueError("%s inventory must be an object" % label)
    meta = inventory.get("meta") or {}
    scan_mode = (meta.get("scan_mode") or "").strip()
    if expected_scan_mode and scan_mode and scan_mode != expected_scan_mode:
        raise ValueError("%s meta.scan_mode mismatch: %s != %s" % (label, scan_mode, expected_scan_mode))

    try:
        import jsonschema
        from jsonschema import Draft7Validator
    except Exception:
        raise RuntimeError(
            "jsonschema is required for schema validation. Install jsonschema or run without --schema."
        )

    validator = Draft7Validator(schema)
    errors = list(validator.iter_errors(inventory))
    if not errors:
        return
    errors = sorted(errors, key=lambda e: (list(e.path), to_text(e.message)))
    shown = errors[:30]
    lines = []
    for e in shown:
        p = ".".join([to_text(x) for x in list(e.path)]) if list(e.path) else "(root)"
        lines.append("%s: %s" % (p, to_text(e.message)))
    if len(errors) > len(shown):
        lines.append("...（%d 条未展示）" % (len(errors) - len(shown)))
    raise ValueError("%s inventory schema validation failed:\n%s" % (label, "\n".join(lines)))


def render_audit_markdown(project, runtime, project_path, runtime_path, schema_path, max_items, focus_prefixes):
    focus_prefixes = [to_text(p).strip() for p in (focus_prefixes or []) if to_text(p).strip()]
    creation_time = local_today_cn()
    updated_time = local_today_cn()

    p_meta = (project or {}).get("meta") or {}
    r_meta = (runtime or {}).get("meta") or {}

    def is_focused(record):
        if not focus_prefixes:
            return False
        mid = to_text((record or {}).get("module_id")).strip()
        if not mid:
            return False
        for p in focus_prefixes:
            if mid.startswith(p):
                return True
        return False

    p_entities = project.get("entities") or []
    r_entities = runtime.get("entities") or []
    p_workflows = project.get("workflows") or []
    r_workflows = runtime.get("workflows") or []
    p_catalog = (project.get("catalog") or {})
    r_catalog = (runtime.get("catalog") or {})
    p_security = (project.get("security") or {})
    r_security = (runtime.get("security") or {})
    p_ui = (project.get("ui_routes") or {})
    r_ui = (runtime.get("ui_routes") or {})

    p_entities_by_id = make_index(p_entities, "type_id")
    r_entities_by_id = make_index(r_entities, "type_id")

    def module_prefix(mid):
        m = to_text(mid).strip()
        if not m:
            return ""
        parts = [p for p in m.split(".") if p]
        if len(parts) >= 2:
            return "%s.%s" % (parts[0], parts[1])
        return parts[0] if parts else ""

    p_custom = []
    for e in p_entities:
        mid = module_prefix((e or {}).get("module_id"))
        if mid == "maitux" or mid.startswith("maitux."):
            p_custom.append(to_text((e or {}).get("type_id")).strip())
    p_custom = [x for x in p_custom if x]
    p_custom = sorted(set(p_custom))

    p_core = []
    for e in p_entities:
        mid = module_prefix((e or {}).get("module_id"))
        if mid.startswith("senaite.") or mid == "senaite":
            p_core.append(to_text((e or {}).get("type_id")).strip())
    p_core = sorted([x for x in set(p_core) if x])

    p_workflows_by_id = make_index(p_workflows, "workflow_id")
    r_workflows_by_id = make_index(r_workflows, "workflow_id")

    def list_pairs(keys, left_index, right_index, left_field, right_field):
        lines = []
        for k in keys[:max_items]:
            l = left_index.get(k) or {}
            r = right_index.get(k) or {}
            lv = to_text(l.get(left_field)).strip()
            rv = to_text(r.get(right_field)).strip()
            if not rv:
                rv = "-"
            if not lv:
                lv = "-"
            lines.append("- %s | project=%s | runtime=%s" % (to_text(k), lv, rv))
        if len(keys) > max_items:
            lines.append("- ...（%d 条未展示）" % (len(keys) - max_items))
        return "\n".join(lines)

    def list_presence(keys, right_index):
        lines = []
        for k in keys[:max_items]:
            ok = "Y" if k in right_index else "N"
            lines.append("- %s | runtime=%s" % (to_text(k), ok))
        if len(keys) > max_items:
            lines.append("- ...（%d 条未展示）" % (len(keys) - max_items))
        return "\n".join(lines)

    p_indexes = make_index(p_catalog.get("indexes") or [], "name")
    r_indexes = make_index(r_catalog.get("indexes") or [], "name")
    p_metadata = make_index(p_catalog.get("metadata") or [], "name")
    r_metadata = make_index(r_catalog.get("metadata") or [], "name")

    lines = []
    lines.append("---")
    lines.append("文档创建时间：%s" % to_text(creation_time))
    lines.append("标注日期/更新时间：%s" % to_text(updated_time))
    lines.append("project：%s" % to_text(project_path))
    lines.append("runtime：%s" % to_text(runtime_path))
    if schema_path:
        lines.append("schema：%s" % to_text(schema_path))
    if focus_prefixes:
        lines.append("聚焦模块前缀：%s" % ", ".join(focus_prefixes))
    lines.append("---")
    lines.append("")
    lines.append("# capability_inventory 抽样核对（验收用）")
    lines.append("")
    lines.append("## 1. Meta 快照")
    lines.append("")
    lines.append("- project.scan_mode=%s, generated_at=%s" % (to_text(p_meta.get("scan_mode")), to_text(p_meta.get("generated_at"))))
    lines.append("- runtime.scan_mode=%s, generated_at=%s" % (to_text(r_meta.get("scan_mode")), to_text(r_meta.get("generated_at"))))
    lines.append("")

    lines.append("## 2. portal_types 抽样核对")
    lines.append("")
    lines.append("### 2.1 项目自定义 types（以 module_id=maitux.* 判定）")
    lines.append(list_presence(p_custom, r_entities_by_id) or "- （无）")
    lines.append("")
    lines.append("### 2.2 核心 types 抽样（按 type_id 排序取前 %d）" % min(20, max_items))
    core_sample = p_core[: min(20, len(p_core))]
    lines.append(list_pairs(core_sample, p_entities_by_id, r_entities_by_id, "title", "title") or "- （无）")
    lines.append("")

    lines.append("## 3. portal_workflow 抽样核对（按 workflow_id 排序取前 %d）" % min(10, max_items))
    lines.append("")
    wf_keys = sorted(set(list(p_workflows_by_id.keys()) + list(r_workflows_by_id.keys())))
    wf_sample = wf_keys[: min(10, len(wf_keys))]
    wf_lines = []
    for wf_id in wf_sample:
        pw = p_workflows_by_id.get(wf_id) or {}
        rw = r_workflows_by_id.get(wf_id) or {}
        wf_lines.append("- %s | project.bound_types=%d | runtime.bound_types=%d" % (to_text(wf_id), len(pw.get("bound_types") or []), len(rw.get("bound_types") or [])))
    lines.append("\n".join(wf_lines) or "- （无）")
    lines.append("")

    lines.append("## 4. portal_catalog 抽样核对（按 name 排序取前 %d）" % min(20, max_items))
    lines.append("")
    idx_keys = sorted(set(list(p_indexes.keys()) + list(r_indexes.keys())))
    md_keys = sorted(set(list(p_metadata.keys()) + list(r_metadata.keys())))
    lines.append("### 4.1 Indexes（name/type）")
    lines.append(list_pairs(idx_keys[: min(20, len(idx_keys))], p_indexes, r_indexes, "type", "type") or "- （无）")
    lines.append("")
    lines.append("### 4.2 Metadata（name）")
    lines.append(list_presence(md_keys[: min(20, len(md_keys))], r_metadata) or "- （无）")
    lines.append("")

    lines.append("## 5. ui_routes 抽样核对（按 name 取样）")
    lines.append("")
    p_actions = p_ui.get("actions") or []
    r_actions = r_ui.get("actions") or []
    p_viewlets = p_ui.get("viewlets") or []
    r_viewlets = r_ui.get("viewlets") or []
    p_views = p_ui.get("views") or []
    r_views = r_ui.get("views") or []
    lines.append("- actions: project=%d, runtime=%d" % (len(p_actions), len(r_actions)))
    lines.append("- viewlets: project=%d, runtime=%d" % (len(p_viewlets), len(r_viewlets)))
    lines.append("- views: project=%d, runtime=%d" % (len(p_views), len(r_views)))
    lines.append("")
    p_viewlet_names = sorted(set([to_text((v or {}).get("name")).strip() for v in p_viewlets if to_text((v or {}).get("name")).strip()]))
    lines.append("### 5.1 Viewlets（按 name 排序取前 %d）" % min(20, max_items))
    lines.append(list_presence(p_viewlet_names[: min(20, len(p_viewlet_names))], make_index(r_viewlets, "name")) or "- （无）")
    lines.append("")
    p_view_names = sorted(set([to_text((v or {}).get("name")).strip() for v in p_views if to_text((v or {}).get("name")).strip()]))
    lines.append("### 5.2 Views（按 name 排序取前 %d）" % min(20, max_items))
    lines.append(list_presence(p_view_names[: min(20, len(p_view_names))], make_index(r_views, "name")) or "- （无）")
    lines.append("")

    if focus_prefixes:
        lines.append("## 6. 聚焦模块快照（added 展开口径）")
        lines.append("")
        focused_entities = sorted(
            [to_text((e or {}).get("type_id")).strip() for e in r_entities if is_focused(e) and to_text((e or {}).get("type_id")).strip()]
        )
        lines.append("### 6.1 Runtime Entities（聚焦模块内，按 type_id）")
        lines.append(format_list(focused_entities, max_items).rstrip() or "- （无）")
        lines.append("")

    return "\n".join(lines).strip() + "\n"




def make_index(items, key_field):
    indexed = {}
    for item in items or []:
        key = None
        try:
            key = (item or {}).get(key_field)
        except Exception:
            key = None
        if not key:
            continue
        indexed[key] = item
    return indexed


def diff_indexed(left_index, right_index):
    left_keys = set(left_index.keys())
    right_keys = set(right_index.keys())

    added = [right_index[k] for k in sorted(right_keys - left_keys)]
    removed = [left_index[k] for k in sorted(left_keys - right_keys)]

    changed = []
    for k in sorted(left_keys & right_keys):
        a = left_index[k]
        b = right_index[k]
        if a == b:
            continue
        changed_fields = sorted(set(a.keys()) | set(b.keys()))
        changed.append({"key": k, "changed_fields": changed_fields, "before": a, "after": b})

    return {"added": added, "removed": removed, "changed": changed}


def make_index_by(items, key_func):
    indexed = {}
    for item in items or []:
        key = None
        try:
            key = key_func(item)
        except Exception:
            key = None
        key = to_text(key).strip()
        if not key:
            continue
        indexed[key] = item
    return indexed


def action_key(action):
    category = to_text((action or {}).get("category")).strip()
    action_id = to_text((action or {}).get("id")).strip()
    if category and action_id:
        return "%s/%s" % (category, action_id)
    return action_id or category


def summarize_section(name, section):
    if not isinstance(section, dict):
        return {"name": name, "added": 0, "removed": 0, "changed": 0}
    return {
        "name": name,
        "added": len(section.get("added") or []),
        "removed": len(section.get("removed") or []),
        "changed": len(section.get("changed") or []),
    }


def format_list(items, max_items):
    shown = items[:max_items]
    lines = []
    for it in shown:
        lines.append("- %s" % to_text(it))
    if len(items) > max_items:
        lines.append("- ...（%d 条未展示）" % (len(items) - max_items))
    return "\n".join(lines) + ("\n" if lines else "")


def changed_keys(changed_list, max_items):
    items = []
    for c in changed_list or []:
        key = to_text((c or {}).get("key")).strip()
        fields = (c or {}).get("changed_fields") or []
        fields_text = ", ".join([to_text(x) for x in fields][:10])
        if len(fields) > 10:
            fields_text = fields_text + ", ..."
        if fields_text:
            items.append("%s（%s）" % (key, fields_text))
        else:
            items.append(key)
    return format_list(items, max_items)


def extract_action_identifiers(actions):
    ids = []
    for a in actions or []:
        ids.append(action_key(a))
    return ids


def render_diff_markdown(diff, json_path, max_items, focus_prefixes, md_mode):
    focus_prefixes = [to_text(p).strip() for p in (focus_prefixes or []) if to_text(p).strip()]
    md_mode = (to_text(md_mode).strip().lower() or "risk")
    if md_mode not in ("risk", "full"):
        md_mode = "risk"

    def is_focused(record):
        if not focus_prefixes:
            return False
        mid = to_text((record or {}).get("module_id")).strip()
        if not mid:
            return False
        for p in focus_prefixes:
            if mid.startswith(p):
                return True
        return False

    def filter_added(records):
        if not focus_prefixes:
            return records
        return [r for r in records if is_focused(r)]

    def include_added_details():
        if md_mode == "full":
            return True
        return bool(focus_prefixes)

    meta = diff.get("meta") or {}
    gen_at = to_text(meta.get("generated_at")).strip() or utc_now_iso()
    existing_creation = read_existing_creation_time(resolve_md_output_path_from_json(json_path))
    creation_time = existing_creation or local_today_cn()
    updated_time = local_today_cn()

    sections = []
    sections.append(summarize_section("entities", diff.get("entities") or {}))
    sections.append(summarize_section("workflows", diff.get("workflows") or {}))

    catalog = diff.get("catalog") or {}
    sections.append(summarize_section("catalog.indexes", (catalog.get("indexes") or {})))
    sections.append(summarize_section("catalog.metadata", (catalog.get("metadata") or {})))

    security = diff.get("security") or {}
    sections.append(summarize_section("security.permissions", (security.get("permissions") or {})))
    sections.append(summarize_section("security.rolemap", (security.get("rolemap") or {})))

    ui = diff.get("ui_routes") or {}
    sections.append(summarize_section("ui_routes.actions", (ui.get("actions") or {})))
    sections.append(summarize_section("ui_routes.viewlets", (ui.get("viewlets") or {})))
    sections.append(summarize_section("ui_routes.views", (ui.get("views") or {})))

    lines = []
    lines.append("---")
    lines.append("文档创建时间：%s" % to_text(creation_time))
    lines.append("标注日期/更新时间：%s" % to_text(updated_time))
    lines.append("来源：%s" % to_text(json_path))
    lines.append("generated_at：%s" % to_text(gen_at))
    if focus_prefixes:
        lines.append("聚焦模块前缀：%s" % ", ".join(focus_prefixes))
    lines.append("md_mode：%s" % to_text(md_mode))
    lines.append("---")
    lines.append("")
    lines.append("# capability_inventory.diff 摘要")
    lines.append("")
    if md_mode == "risk":
        lines.append("说明：risk 模式默认只展开 removed/changed；added 仅在设置聚焦模块前缀时展开。")
        lines.append("")
    lines.append("## 1. 总览")
    lines.append("")
    lines.append("| 区域 | added | removed | changed |")
    lines.append("|---|---:|---:|---:|")
    for s in sections:
        lines.append("| %s | %d | %d | %d |" % (s["name"], s["added"], s["removed"], s["changed"]))
    lines.append("")

    def render_block(title, section, key_label, key_extractor):
        added = filter_added(section.get("added") or [])
        if not include_added_details():
            added = []
        removed = section.get("removed") or []
        changed = section.get("changed") or []

        lines.append("## %s" % title)
        lines.append("")
        if removed:
            keys = [key_extractor(r) for r in removed]
            lines.append("### removed（%d）" % len(keys))
            lines.append(format_list(keys, max_items).rstrip())
            lines.append("")
        if changed:
            lines.append("### changed（%d）" % len(changed))
            lines.append(changed_keys(changed, max_items).rstrip())
            lines.append("")
        if added:
            keys = [key_extractor(r) for r in added]
            lines.append("### added（%d）" % len(keys))
            lines.append(format_list(keys, max_items).rstrip())
            lines.append("")
        if not removed and not changed and not added:
            lines.append("- 无差异")
            lines.append("")

    entities = diff.get("entities") or {}
    render_block("2. Entities（按 type_id）", entities, "type_id", lambda r: to_text((r or {}).get("type_id")).strip())

    workflows = diff.get("workflows") or {}
    render_block("3. Workflows（按 workflow_id）", workflows, "workflow_id", lambda r: to_text((r or {}).get("workflow_id")).strip())

    sec_perm = (security.get("permissions") or {})
    render_block("4. Security / Permissions（按 id）", sec_perm, "id", lambda r: to_text((r or {}).get("id")).strip())

    sec_rolemap = (security.get("rolemap") or {})
    render_block("5. Security / Rolemap（按 role）", sec_rolemap, "role", lambda r: to_text((r or {}).get("role")).strip())

    cat_indexes = (catalog.get("indexes") or {})
    render_block("6. Catalog / Indexes（按 name）", cat_indexes, "name", lambda r: to_text((r or {}).get("name")).strip())

    cat_metadata = (catalog.get("metadata") or {})
    render_block("7. Catalog / Metadata（按 name）", cat_metadata, "name", lambda r: to_text((r or {}).get("name")).strip())

    ui_actions = (ui.get("actions") or {})
    lines.append("## 8. UI Routes / Actions（按 category/id）")
    lines.append("")
    added = filter_added(ui_actions.get("added") or [])
    if not include_added_details():
        added = []
    removed = ui_actions.get("removed") or []
    changed = ui_actions.get("changed") or []
    if removed:
        lines.append("### removed（%d）" % len(removed))
        lines.append(format_list(extract_action_identifiers(removed), max_items).rstrip())
        lines.append("")
    if changed:
        lines.append("### changed（%d）" % len(changed))
        lines.append(changed_keys(changed, max_items).rstrip())
        lines.append("")
    if added:
        lines.append("### added（%d）" % len(added))
        lines.append(format_list(extract_action_identifiers(added), max_items).rstrip())
        lines.append("")
    if not removed and not changed and not added:
        lines.append("- 无差异")
        lines.append("")

    viewlets = (ui.get("viewlets") or {})
    render_block("9. UI Routes / Viewlets（按 name）", viewlets, "name", lambda r: to_text((r or {}).get("name")).strip())

    views = (ui.get("views") or {})
    render_block("10. UI Routes / Views（按 name）", views, "name", lambda r: to_text((r or {}).get("name")).strip())

    return "\n".join(lines).strip() + "\n"


def resolve_md_output_path(out_dir_or_file):
    lowered = (
        out_dir_or_file.lower()
        if hasattr(out_dir_or_file, "lower")
        else str(out_dir_or_file).lower()
    )
    if lowered.endswith(".md"):
        return out_dir_or_file
    if lowered.endswith(".json"):
        base = os.path.basename(out_dir_or_file)
        if base == "capability_inventory.diff.json":
            md_base = "capability_inventory.diff.md"
        else:
            md_base = os.path.splitext(base)[0] + ".md"
        return os.path.join(os.path.dirname(out_dir_or_file), md_base)
    return os.path.join(out_dir_or_file, "capability_inventory.diff.md")


def resolve_md_output_path_from_json(json_path):
    return resolve_md_output_path(json_path)


def resolve_output_path(output_dir_or_file):
    lowered = (
        output_dir_or_file.lower()
        if hasattr(output_dir_or_file, "lower")
        else str(output_dir_or_file).lower()
    )
    if lowered.endswith(".json"):
        return output_dir_or_file
    return os.path.join(output_dir_or_file, "capability_inventory.diff.json")


def diff_inventories_generic(
    left_label,
    left_path,
    right_label,
    right_path,
    out_path,
    md_out_path=None,
    max_items=30,
    focus_modules=None,
    md_mode="risk",
    schema_path=None,
    audit_md_out_path=None,
    left_expected_scan_mode=None,
    right_expected_scan_mode=None,
    allow_audit=False,
):
    left = load_json(left_path)
    right = load_json(right_path)

    schema = None
    if schema_path:
        schema = load_json(schema_path)
        validate_inventory_with_schema(left, schema, left_expected_scan_mode, left_label)
        validate_inventory_with_schema(right, schema, right_expected_scan_mode, right_label)

    diff = {
        "meta": {
            "generated_at": utc_now_iso(),
            "left": {
                "path": left_path,
                "label": left_label,
                "scan_mode": (left.get("meta") or {}).get("scan_mode") if isinstance(left, dict) else None,
            },
            "right": {
                "path": right_path,
                "label": right_label,
                "scan_mode": (right.get("meta") or {}).get("scan_mode") if isinstance(right, dict) else None,
            },
        }
    }

    diff["entities"] = diff_indexed(
        make_index(left.get("entities"), "type_id") if isinstance(left, dict) else {},
        make_index(right.get("entities"), "type_id") if isinstance(right, dict) else {},
    )

    diff["workflows"] = diff_indexed(
        make_index(left.get("workflows"), "workflow_id") if isinstance(left, dict) else {},
        make_index(right.get("workflows"), "workflow_id") if isinstance(right, dict) else {},
    )

    left_catalog = (left.get("catalog") or {}) if isinstance(left, dict) else {}
    right_catalog = (right.get("catalog") or {}) if isinstance(right, dict) else {}
    diff["catalog"] = {
        "indexes": diff_indexed(
            make_index(left_catalog.get("indexes"), "name"),
            make_index(right_catalog.get("indexes"), "name"),
        ),
        "metadata": diff_indexed(
            make_index(left_catalog.get("metadata"), "name"),
            make_index(right_catalog.get("metadata"), "name"),
        ),
    }

    left_security = (left.get("security") or {}) if isinstance(left, dict) else {}
    right_security = (right.get("security") or {}) if isinstance(right, dict) else {}
    diff["security"] = {
        "permissions": diff_indexed(
            make_index(left_security.get("permissions"), "id"),
            make_index(right_security.get("permissions"), "id"),
        ),
        "rolemap": diff_indexed(
            make_index(left_security.get("rolemap"), "role"),
            make_index(right_security.get("rolemap"), "role"),
        ),
    }

    left_ui = (left.get("ui_routes") or {}) if isinstance(left, dict) else {}
    right_ui = (right.get("ui_routes") or {}) if isinstance(right, dict) else {}
    diff["ui_routes"] = {
        "actions": diff_indexed(
            make_index_by(left_ui.get("actions"), action_key),
            make_index_by(right_ui.get("actions"), action_key),
        ),
        "viewlets": diff_indexed(
            make_index(left_ui.get("viewlets"), "name"),
            make_index(right_ui.get("viewlets"), "name"),
        ),
        "views": diff_indexed(
            make_index(left_ui.get("views"), "name"),
            make_index(right_ui.get("views"), "name"),
        ),
    }

    write_json(out_path, diff)
    if md_out_path:
        md_text = render_diff_markdown(
            diff,
            out_path,
            max_items=max_items,
            focus_prefixes=focus_modules,
            md_mode=md_mode,
        )
        write_markdown(md_out_path, md_text)
    if audit_md_out_path:
        if not allow_audit:
            raise ValueError("audit-md-out only supported for project vs runtime diff")
        audit_text = render_audit_markdown(
            left,
            right,
            project_path=left_path,
            runtime_path=right_path,
            schema_path=schema_path,
            max_items=max_items,
            focus_prefixes=focus_modules,
        )
        write_markdown(audit_md_out_path, audit_text)
    return out_path


def diff_inventories(
    project_path,
    runtime_path,
    out_path,
    md_out_path=None,
    max_items=30,
    focus_modules=None,
    md_mode="risk",
    schema_path=None,
    audit_md_out_path=None,
):
    return diff_inventories_generic(
        "project",
        project_path,
        "runtime",
        runtime_path,
        out_path,
        md_out_path=md_out_path,
        max_items=max_items,
        focus_modules=focus_modules,
        md_mode=md_mode,
        schema_path=schema_path,
        audit_md_out_path=audit_md_out_path,
        left_expected_scan_mode="project",
        right_expected_scan_mode="runtime",
        allow_audit=True,
    )


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", dest="project_path", default=None)
    parser.add_argument("--runtime", dest="runtime_path", default=None)
    parser.add_argument("--left", dest="left_path", default=None)
    parser.add_argument("--right", dest="right_path", default=None)
    parser.add_argument("--left-name", dest="left_name", default=None)
    parser.add_argument("--right-name", dest="right_name", default=None)
    parser.add_argument("--expected-scan-mode", dest="expected_scan_mode", default=None, choices=["project", "runtime"])
    parser.add_argument("--out", dest="out", required=True)
    parser.add_argument("--md-out", dest="md_out", default=None)
    parser.add_argument("--no-md", dest="no_md", action="store_true", default=False)
    parser.add_argument("--md-mode", dest="md_mode", default="risk", choices=["risk", "full"])
    parser.add_argument("--max-items", dest="max_items", type=int, default=30)
    parser.add_argument("--focus-modules", dest="focus_modules", default=None)
    parser.add_argument("--schema", dest="schema", default=None)
    parser.add_argument("--no-schema", dest="no_schema", action="store_true", default=False)
    parser.add_argument("--audit-md-out", dest="audit_md_out", default=None)
    args = parser.parse_args(argv)

    out_path = resolve_output_path(args.out)
    md_out_path = None
    if not args.no_md:
        md_out_path = resolve_md_output_path(args.md_out or out_path)
    schema_path = None
    if not args.no_schema:
        if args.schema:
            schema_path = args.schema
        else:
            schema_path = find_default_schema_path()
            if not schema_path:
                schema_path = None

    audit_md_out_path = None
    if args.audit_md_out:
        audit_md_out_path = args.audit_md_out
    focus_modules = []
    if args.focus_modules:
        focus_modules = [p.strip() for p in to_text(args.focus_modules).split(",") if p.strip()]

    if args.project_path and args.runtime_path:
        return diff_inventories(
            args.project_path,
            args.runtime_path,
            out_path,
            md_out_path=md_out_path,
            max_items=max(1, int(args.max_items or 30)),
            focus_modules=focus_modules,
            md_mode=args.md_mode,
            schema_path=schema_path,
            audit_md_out_path=audit_md_out_path,
        )

    if args.left_path and args.right_path:
        if audit_md_out_path:
            raise ValueError("audit-md-out only supported for --project/--runtime mode")
        left_label = (args.left_name or "left").strip() or "left"
        right_label = (args.right_name or "right").strip() or "right"
        expected = args.expected_scan_mode
        return diff_inventories_generic(
            left_label,
            args.left_path,
            right_label,
            args.right_path,
            out_path,
            md_out_path=md_out_path,
            max_items=max(1, int(args.max_items or 30)),
            focus_modules=focus_modules,
            md_mode=args.md_mode,
            schema_path=schema_path,
            audit_md_out_path=None,
            left_expected_scan_mode=expected,
            right_expected_scan_mode=expected,
            allow_audit=False,
        )

    parser.error("Either (--project and --runtime) or (--left and --right) must be provided")


if __name__ == "__main__":
    import sys

    main(sys.argv[1:])

