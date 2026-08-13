# -*- coding: utf-8 -*-
#
# Monkey-patches to extend Senaite's InterimFieldsField with
# "list" and "calculated" result types.
#
# Key design:
#   list       鈫?"multivalue" 鈫?MultiValue component (multiple inputs 卤)
#   calculated 鈫?"readonly"   鈫?ReadonlyField, auto-computed via sub-formula
#   setInterimValue auto-averages list values before storage
#   After any interim change, all Calculated interims are re-evaluated

import json
from copy import deepcopy

from bika.lims import bikaMessageFactory as _
from maitux.calcenhance.formula_support import get_additional_formula_globals


def apply_patches():
    """Apply monkey-patches to core Senaite types."""
    _patch_core_formula_globals()
    _patch_interimfields_schema()
    _patch_interimfields_result_types()
    _patch_dexterity_interimfields_schema()
    _patch_folder_item()
    _patch_is_multi_interim()
    _patch_get_formatted_interim()
    _patch_set_interim_value()


def _patch_core_formula_globals():
    """给原生 Calculation 与 Analysis 公式执行链补充自定义函数。"""
    from senaite.core.content import calculation as calculation_module
    from bika.lims.content import abstractanalysis as abstractanalysis_module

    original_get_globals = calculation_module.getGlobals

    def patched_get_globals(imports=None, **kwargs):
        # 中文注释：先保留原生白名单和 imports，再合并自定义公式函数。
        globals_dict = original_get_globals(imports=imports, **kwargs)
        globals_dict.update(get_additional_formula_globals())
        return globals_dict

    calculation_module.getGlobals = patched_get_globals
    abstractanalysis_module.getGlobals = patched_get_globals


# ==============================================================================
# SCHEMA PATCH 鈥?Add "formula" subfield for Calculated type interims
# ==============================================================================

def _patch_interimfields_schema():
    """Add 'formula' subfield to InterimFieldsField for Calculated type.

    Formula column will now appear in ALL InterimFieldsField usages
    (Calculation, AnalysisService, etc.) but only has effect when the
    row is type='calculated'. The original testSubfieldCondition is
    NOT patched 鈥?`getSubfields` is patched to always include formula.
    """
    import sys as _sys
    _sys.stderr.write("maitux: patching InterimFieldsField schema...\n")
    _sys.stderr.flush()

    from bika.lims.browser.fields.interimfieldsfield import InterimFieldsField

    props = InterimFieldsField._properties
    existing = list(props["subfields"])
    if "formula" not in existing:
        props["subfields"] = tuple(existing + ["formula"])
        _sys.stderr.write("maitux: formula added to subfields\n")

    props.setdefault("subfield_labels", {})["formula"] = _("Formula")
    props.setdefault("subfield_types", {})["formula"] = "string"
    props.setdefault("subfield_sizes", {})["formula"] = 50
    props.setdefault("subfield_maxlength", {})["formula"] = -1
    props.setdefault("subfield_validators", {})["formula"] = "interimfieldsvalidator"

    # Patch getSubfields to always include formula
    # Archetypes copies _properties from class to instance at init time,
    # so self._properties may NOT have our "formula" addition.
    # We ALWAYS append "formula" to avoid relying on instance _properties.
    _original_getSubfields = InterimFieldsField.getSubfields

    def patched_getSubfields(self):
        subfields = list(_original_getSubfields(self))
        if "formula" not in subfields:
            subfields.append("formula")
        return tuple(subfields)

    InterimFieldsField.getSubfields = patched_getSubfields
    _sys.stderr.write("maitux: schema patch done\n")
    _sys.stderr.flush()


# ==============================================================================
# VOCABULARY PATCH 鈥?Add "list" and "calculated" to result_type dropdown
# ==============================================================================

def _patch_interimfields_result_types():
    """Add 'list' and 'calculated' to InterimFieldsField result_type vocabulary."""
    from Products.Archetypes import DisplayList
    from bika.lims.browser.fields.interimfieldsfield import InterimFieldsField

    vocab = InterimFieldsField._properties["subfield_vocabularies"]
    result_type_vocab = vocab["result_type"]

    if isinstance(result_type_vocab, DisplayList):
        result_type_vocab.add("list", _("List (array)"))
        result_type_vocab.add("calculated", _("Calculated"))


# ==============================================================================
# DEXTERITY SCHEMA PATCH 鈥?Add "formula" to IInterimField interface
# ==============================================================================

def _patch_dexterity_interimfields_schema():
    """Add 'formula' field to the Dexterity IInterimField schema.

    The Calculation edit form uses Dexterity InterimFields with IInterimField
    schema (via DataGridWidgetFactory). Adding 'formula' to this interface
    makes the Formula column appear in the datagrid widget automatically.

    We create a subclass of IInterimField to add the formula field, then
    replace InterimFields.value_type with a new DataGridRow using the patched
    schema. Simply setting attributes on IInterimField doesn't work because
    zope.interface's metaclass processes fields only at class creation time.
    """
    import sys as _sys
    _sys.stderr.write("maitux: patching Dexterity IInterimField schema...\n")
    _sys.stderr.flush()

    try:
        from senaite.core.schema.interimfields import IInterimField
        from senaite.core.schema.interimfields import InterimFields
    except ImportError:
        # 当前版本没有 Dexterity interimfields 模块时直接跳过，
        # 避免因为版本差异导致站点启动失败。
        _sys.stderr.write(
            "maitux: Dexterity interimfields schema not available, skip patch\n")
        _sys.stderr.flush()
        return

    from senaite.core.schema.fields import DataGridRow
    from zope import schema as _schema
    from bika.lims import senaiteMessageFactory as _dx

    # Create a patched interface that extends IInterimField with formula
    class IInterimFieldPatched(IInterimField):
        formula = _schema.TextLine(
            title=_dx(
                u"label_interim_formula",
                default=u"Formula"
            ),
            description=_dx(
                u"description_interim_formula",
                default=u"Sub-formula using [keyword] references"
            ),
            required=False,
            default=u""
        )

    # Replace the value_type with new schema
    InterimFields.value_type = DataGridRow(schema=IInterimFieldPatched)

    _sys.stderr.write("maitux: IInterimFieldPatched names: %s\n"
                      % str(list(IInterimFieldPatched.names())))
    _sys.stderr.write("maitux: InterimFields.value_type updated\n")
    _sys.stderr.flush()


# ==============================================================================
# FOLDERITEM PATCH 鈥?Map custom types to ReactJS components
# ==============================================================================

def _patch_folder_item():
    """Patch _folder_item_calculation to map list鈫抦ultivalue, calculated鈫抮eadonly."""
    from bika.lims.browser.analyses import view as analysis_view

    original_folderitem = analysis_view.AnalysesView._folder_item_calculation

    def patched_folderitem(self, analysis_brain, item):
        original_folderitem(self, analysis_brain, item)

        interim_fields = item.get("interimfields", [])
        for interim_field in interim_fields:
            keyword = interim_field.get("keyword", "")
            result_type = interim_field.get("result_type", "")

            if result_type == "list":
                if keyword in item:
                    value = item[keyword].get("value", "")
                    if value:
                        try:
                            parsed = json.loads(str(value))
                            if not isinstance(parsed, list):
                                value = json.dumps([str(value)])
                        except (ValueError, TypeError):
                            value = json.dumps([str(value)])
                    item[keyword] = deepcopy(item[keyword])
                    item[keyword]["value"] = value
                    item[keyword]["result_type"] = "multivalue"
                    item[keyword]["_orig_result_type"] = "list"
                    if keyword in item.get("choices", {}):
                        del item["choices"][keyword]

            elif result_type == "calculated":
                if keyword in item:
                    item[keyword] = deepcopy(item[keyword])
                    item[keyword]["result_type"] = "readonly"
                    item[keyword]["_orig_result_type"] = "calculated"
                    if keyword in item.get("choices", {}):
                        del item["choices"][keyword]

    analysis_view.AnalysesView._folder_item_calculation = patched_folderitem


# ==============================================================================
# IS_MULTI_INTERIM PATCH 鈥?Treat "list" as multi-value
# ==============================================================================

def _patch_is_multi_interim():
    """Patch is_multi_interim to treat 'list' as a multi-value type."""
    from bika.lims.browser.analyses import view as analysis_view

    original_is_multi = analysis_view.AnalysesView.is_multi_interim

    def patched_is_multi_interim(self, interim):
        if interim.get("result_type", "") == "list":
            return True
        return original_is_multi(self, interim)

    analysis_view.AnalysesView.is_multi_interim = patched_is_multi_interim


# ==============================================================================
# GET_FORMATTED_INTERIM PATCH 鈥?Display calculated values
# ==============================================================================

def _patch_get_formatted_interim():
    """Patch get_formatted_interim for 'calculated' type display."""
    from bika.lims.browser.analyses import view as analysis_view

    original_formatted = analysis_view.AnalysesView.get_formatted_interim

    def patched_get_formatted_interim(self, interim):
        if interim.get("result_type", "") == "calculated":
            raw_value = interim.get("value", "") or ""
            from bika.lims.browser.analyses.view import formatDecimalMark
            return formatDecimalMark(raw_value, self.dmk)
        return original_formatted(self, interim)

    analysis_view.AnalysesView.get_formatted_interim = patched_get_formatted_interim


# ==============================================================================
# SET_INTERIM_VALUE PATCH 鈥?Auto-average list + re-evaluate calculated
# ==============================================================================

def _patch_set_interim_value():
    """Patch setInterimValue:
    - Auto-averages list-type values on save
    - After saving, re-evaluates all Calculated-type interims
    """

    def patched_setInterimValue(self, keyword, value):
        # Pre-process value (auto-average for list)
        value = _preprocess_value(self, keyword, value)

        # --- Original save logic (inline) ---
        import json as _j
        from bika.lims.utils import string_types as _string_types
        if value is None:
            value = ""
        elif isinstance(value, _string_types):
            value = value.strip()
        elif isinstance(value, (list, tuple, set, dict)):
            value = _j.dumps(value)

        interims = self.getInterimFields()
        for interim in interims:
            if interim.get("keyword") == keyword:
                interim["value"] = str(value)
        self.setInterimFields(interims)
        # --- End original save logic ---

        # Re-evaluate all Calculated-type interims
        _evaluate_calculated_interims(self)

    try:
        from bika.lims.content.abstractanalysis import AbstractBaseAnalysis
        setattr(AbstractBaseAnalysis, "setInterimValue", patched_setInterimValue)
    except Exception:
        pass


def _preprocess_value(self, keyword, value):
    """Auto-average list-type values before storage."""
    interim_type = None
    try:
        for i in self.getInterimFields():
            if i.get("keyword") == keyword:
                interim_type = i.get("result_type", "")
                break
    except Exception:
        pass

    if interim_type != "list" or not value:
        return value

    # Parse JSON array and compute average
    try:
        values = json.loads(str(value))
        if isinstance(values, list) and values:
            numeric = []
            for v in values:
                try:
                    numeric.append(float(str(v)))
                except (ValueError, TypeError):
                    pass
            if numeric:
                return sum(numeric) / len(numeric)
    except (ValueError, TypeError):
        pass

    # Fallback: comma/newline/pipe separated
    parts = [v.strip() for v in str(value).replace(
        "\r\n", "\n").replace("|", "\n").split("\n") if v.strip()]
    if not parts:
        parts = [v.strip() for v in str(value).split(",") if v.strip()]
    numeric = []
    for v in parts:
        try:
            numeric.append(float(v))
        except (ValueError, TypeError):
            pass
    if numeric:
        return sum(numeric) / len(numeric)

    return value


# ==============================================================================
# CALCULATED INTERIM EVALUATION ENGINE
# ==============================================================================

def _evaluate_calculated_interims(self):
    """Re-evaluate all Calculated-type interim fields in dependency order.

    1. Builds a dependency graph from formula [keyword] references
    2. Topologically sorts Calculated interims
    3. Evaluates in order, so DilutionFactor is ready when Content1/2 need it
    """
    import bika.lims.api as api
    import re

    interims = self.getInterimFields()
    if not interims:
        return

    # --- Step 1: collect Calculated interims and their dependencies ---
    calculated = []
    keyword_to_idx = {}
    for idx, i in enumerate(interims):
        kw = i.get("keyword", "")
        if kw:
            keyword_to_idx[kw] = idx
        if i.get("result_type", "") == "calculated" and i.get("formula", "").strip():
            calculated.append(i)

    if not calculated:
        return

    # --- Step 2: build value map from current non-calculated values ---
    value_map = {}
    for i in interims:
        kw = i.get("keyword", "")
        val = i.get("value", "")
        if not kw:
            continue
        if i.get("result_type", "") == "calculated":
            # Start with current value or 0
            try:
                value_map[kw] = float(val or 0)
            except (ValueError, TypeError):
                value_map[kw] = val or ""
        else:
            try:
                value_map[kw] = float(val)
            except (ValueError, TypeError):
                value_map[kw] = val

    # --- Step 3: topological sort by dependency ---
    _TOKEN_RE = re.compile(r'\[([A-Za-z_]\w*)\]')

    # Build dependency graph
    deps_of = {}   # keyword 鈫?set of keywords it depends on
    for c in calculated:
        kw = c["keyword"]
        formula = c.get("formula", "") or ""
        deps_of[kw] = set()
        for match in _TOKEN_RE.finditer(formula):
            dep_kw = match.group(1)
            if dep_kw != kw and dep_kw in keyword_to_idx:
                deps_of[kw].add(dep_kw)

    # Kahn's algorithm for topological sort
    in_degree = {c["keyword"]: len(deps_of[c["keyword"]]) for c in calculated}
    # Who depends on whom (reverse graph)
    dependents = {c["keyword"]: set() for c in calculated}
    for kw, deps in deps_of.items():
        for d in deps:
            if d in dependents:
                dependents[d].add(kw)

    queue = [c for c in calculated if in_degree[c["keyword"]] == 0]
    order = []

    while queue:
        c = queue.pop(0)
        order.append(c)
        kw = c["keyword"]
        for dependent in dependents.get(kw, set()):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                # Find the calculated item
                for calc in calculated:
                    if calc["keyword"] == dependent:
                        queue.append(calc)
                        break

    # Append any remaining (circular dependency 鈥?process anyway)
    seen = {c["keyword"] for c in order}
    for c in calculated:
        if c["keyword"] not in seen:
            order.append(c)

    # --- Step 4: evaluate in topological order ---
    changed = False

    for c in order:
        formula = c.get("formula", "") or ""
        kw = c.get("keyword", "")

        if not formula or not kw:
            continue

        # Resolve [keyword] references against current value_map
        expr = formula
        mapping = {}
        for match in _TOKEN_RE.finditer(formula):
            ref_kw = match.group(1)
            val = value_map.get(ref_kw)
            if val is None:
                continue
            placeholder = "[%s]" % ref_kw
            if isinstance(val, (int, float)):
                expr = expr.replace(placeholder, "%%(%s)f" % ref_kw)
                mapping[ref_kw] = float(val)
            elif api.is_floatable(val):
                expr = expr.replace(placeholder, "%%(%s)f" % ref_kw)
                mapping[ref_kw] = float(val)
            else:
                expr = expr.replace(placeholder, "%%(%s)s" % ref_kw)
                mapping[ref_kw] = '"%s"' % str(val)

        if not mapping:
            continue

        try:
            expr = expr % mapping
            safe_globals = {"__builtins__": {
                "abs": abs, "max": max, "min": min, "round": round,
                "sum": sum, "len": len, "pow": pow,
                "True": True, "False": False, "None": None,
                "floor": __import__("math").floor,
                "ceil": __import__("math").ceil,
                "sqrt": __import__("math").sqrt,
                "log": __import__("math").log,
                "log10": __import__("math").log10,
                "exp": __import__("math").exp,
            }}
            # 中文注释：把自定义公式函数提升到 eval 全局作用域，供子公式直接调用。
            safe_globals.update(get_additional_formula_globals())
            result = eval(expr, safe_globals, {})
            new_value = str(result)

            # Update the interim field AND the value_map for downstream deps
            old_value = c.get("value", "")
            if old_value != new_value:
                c["value"] = new_value
                changed = True
                # Update value_map so downstream Calculated get the fresh value
                try:
                    value_map[kw] = float(new_value)
                except (ValueError, TypeError):
                    value_map[kw] = new_value

        except Exception:
            pass  # Formula evaluation error 鈥?leave value as-is

    if changed:
        self.setInterimFields(interims)
