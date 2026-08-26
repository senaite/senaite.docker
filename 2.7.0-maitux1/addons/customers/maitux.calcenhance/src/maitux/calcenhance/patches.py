# -*- coding: utf-8 -*-
#
# Monkey-patches to extend Senaite's InterimFieldsField with
# "list", "calculated", and "calculatedlist" result types.
#
# Key design:
#   list            → "multivalue" → MultiValue component (multiple inputs ±)
#   calculated      → "readonly"   → ReadonlyField, auto-computed via sub-formula
#   calculatedlist  → "readonly"   → element-wise pairing of List arrays
#   List values stored as JSON array; Step 2 auto-averages for bare [KW]
#     references (backward compat), preserves raw array for sum([KW])/max([KW])/...
#   CalculatedList reads raw arrays directly for element-wise computation
#   After any interim change, all Calculated/CalculatedList interims re-evaluated
#
# Cross-Analysis LOOKUP (v1.1):
#   Interim fields marked "cross_referenceable" can be read by sibling
#   analyses on the same AR via the LOOKUP() function:
#     LOOKUP("ServiceKW", "TargetField", "KeyField", key_value)
#   String arrays (non-numeric lists, e.g. solvent names) are supported
#   for key-based matching. Only reads — never writes — sibling data.

import json
from copy import deepcopy

from bika.lims import bikaMessageFactory as _
from Products.Archetypes.event import ObjectEditedEvent as \
    _ATObjectEditedEvent
from zope.event import notify as _notify_event


# [PY2-UNICODE] Not a calculation feature.  This package doubles as our
# Python 2 unicode-safety layer; see the "patches.py 同时承担 Python 2 兼容层"
# section in README.md for the full list and the removal criterion.
def _patch_getlink():
    """Monkey-patch bika.lims.utils.get_link to be Python 2 unicode-safe.

    The original get_link crashes with UnicodeDecodeError when:
    1. u(value) is called on a byte-string value containing CJK
    2. render_html_attributes produces byte-string attr with CJK,
       which then fails in the unicode format string

    This wrapper decodes all byte-string inputs (href, value, kwargs)
    to unicode BEFORE calling the original, so render_html_attributes
    and the final format string operate on unicode-safe data.
    """
    import sys as _sys
    from bika.lims import utils as bika_utils

    _original_get_link = bika_utils.get_link

    def safe_get_link(href, value=None, csrf=True, **kwargs):
        if isinstance(href, str):
            try:
                href = href.decode("utf-8")
            except UnicodeDecodeError:
                pass
        if isinstance(value, str):
            try:
                value = value.decode("utf-8")
            except UnicodeDecodeError:
                pass
        safe_kwargs = {}
        for k, v in kwargs.items():
            if isinstance(v, str):
                try:
                    v = v.decode("utf-8")
                except UnicodeDecodeError:
                    pass
            safe_kwargs[k] = v
        return _original_get_link(href, value=value, csrf=csrf, **safe_kwargs)

    bika_utils.get_link = safe_get_link
    _sys.stderr.write("maitux: get_link patched for Python 2 unicode safety\n")
    _sys.stderr.flush()


def apply_patches():
    """Apply monkey-patches to core Senaite types.

    Order matters: patches that don't import senaite.core (safe on ZCML load)
    go first.  _patch_dexterity_* imports from senaite.core.schema at import
    time and may fail during ZCML bootstrap; it runs last so earlier safe
    patches are already in place.
    """
    # Safe patches (no senaite.core imports at module scope)
    _patch_getlink()           # MUST be before _patch_folder_item
    _patch_interimfields_schema()
    _patch_interimfields_result_types()
    _patch_folder_item()
    _patch_is_multi_interim()
    _patch_get_formatted_interim()
    _patch_format_interim()    # report-side twin of the above
    _patch_set_interim_value()
    _patch_set_interim_fields()
    _patch_calculate_result()
    _patch_validator_interimfields_unicode()

    # senaite.app.listing.ajax imports senaite.core at module scope, so
    # on a cold start this can fail here; an IDatabaseOpenedWithRoot
    # subscriber retries it once every product is loaded.
    try:
        _patch_listing_set_field()
    except Exception:
        pass

    # ISSUE-001: XLSX setup-data importer — keyword uniqueness (upsert)
    # and Method <-> Calculation plural-field writes.  Importing the
    # setupdata module can also fail on a cold start; the
    # IDatabaseOpenedWithRoot subscriber retries it once every product
    # is loaded.
    try:
        _patch_setupdata_import()
    except Exception:
        pass

    # DISABLED: _patch_uidcatalog_unicode() breaks uid_catalog getObject()
    # in UTF-8-native environments (e.g. 8085 MaituxLIMS). The patch stores
    # UUID as the catalog id instead of physical path, causing
    # brain.getObject() → None and breaking UIDReferenceField backreferences.
    # _patch_uidcatalog_unicode()

    # Dexterity patches (import from senaite.core at function scope,
    # may fail during ZCML bootstrap)
    try:
        _patch_dexterity_interimfields_schema()
    except Exception:
        pass


# ==============================================================================
# SCHEMA PATCH — Add "formula" subfield for Calculated type interims
# ==============================================================================

def _patch_interimfields_schema():
    """Add 'formula' subfield to InterimFieldsField for Calculated type.

    Formula column will now appear in ALL InterimFieldsField usages
    (Calculation, AnalysisService, etc.) but only has effect when the
    row is type='calculated'. The original testSubfieldCondition is
    NOT patched — `getSubfields` is patched to always include formula.
    """
    import sys as _sys
    _sys.stderr.write("maitux: patching InterimFieldsField schema...\n")
    _sys.stderr.flush()

    from bika.lims.browser.fields.interimfieldsfield import InterimFieldsField

    props = InterimFieldsField._properties
    # NOTE: accumulate on a single list.  Re-reading props["subfields"] into a
    # stale local between the appends used to make each addition overwrite the
    # previous one (only the last survived in _properties); it went unnoticed
    # because patched_getSubfields below re-adds them all anyway.
    subfields = list(props["subfields"])

    if "formula" not in subfields:
        subfields.append("formula")
        _sys.stderr.write("maitux: formula added to subfields\n")

    props.setdefault("subfield_labels", {})["formula"] = _("Formula")
    props.setdefault("subfield_types", {})["formula"] = "string"
    props.setdefault("subfield_sizes", {})["formula"] = 50
    props.setdefault("subfield_maxlength", {})["formula"] = -1
    props.setdefault("subfield_validators", {})["formula"] = "interimfieldsvalidator"

    # Add cross_referenceable to subfields (allows cross-analysis interim field reading)
    if "cross_referenceable" not in subfields:
        subfields.append("cross_referenceable")
        _sys.stderr.write("maitux: cross_referenceable added to subfields\n")
    props.setdefault("subfield_labels", {})["cross_referenceable"] = _(
        "Cross-ref")
    props.setdefault("subfield_types", {})["cross_referenceable"] = "boolean"
    props.setdefault("subfield_sizes", {})["cross_referenceable"] = 1

    # Add locked: values of a locked interim cannot be changed through the
    # results entry UI.  Meant for instrument-acquired data, which must stay
    # exactly as captured.  Enforcement lives in setInterimValue (see
    # _patch_set_interim_value); this is only the configuration flag.
    if "locked" not in subfields:
        subfields.append("locked")
        _sys.stderr.write("maitux: locked added to subfields\n")
    props.setdefault("subfield_labels", {})["locked"] = _("Locked")
    props.setdefault("subfield_types", {})["locked"] = "boolean"
    props.setdefault("subfield_sizes", {})["locked"] = 1

    props["subfields"] = tuple(subfields)

    # Patch getSubfields to always include formula
    # Archetypes copies _properties from class to instance at init time,
    # so self._properties may NOT have our "formula" addition.
    # We ALWAYS append "formula" to avoid relying on instance _properties.
    _original_getSubfields = InterimFieldsField.getSubfields

    def patched_getSubfields(self):
        subfields = list(_original_getSubfields(self))
        for extra in ("formula", "cross_referenceable", "locked"):
            if extra not in subfields:
                subfields.append(extra)
        return tuple(subfields)

    InterimFieldsField.getSubfields = patched_getSubfields
    _sys.stderr.write("maitux: schema patch done\n")
    _sys.stderr.flush()


# ==============================================================================
# VOCABULARY PATCH — Add "list" and "calculated" to result_type dropdown
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
        result_type_vocab.add("calculatedlist", _("Calculated List"))


# ==============================================================================
# DEXTERITY SCHEMA PATCH — Add "formula" and "cross_referenceable" to IInterimField
# ==============================================================================

def _patch_datagrid_crossref_header():
    """Patch DataGridWidget.update() to set the boolean column headers.

    Bool subfields carry title="" to suppress the per-cell labels rendered by
    CheckBoxWidget; this patch restores the column header labels.
    """
    from senaite.core.z3cform.widgets.datagrid.datagrid import DataGridWidget

    _original_update = DataGridWidget.update

    _HEADERS = {
        "cross_referenceable": u"Cross-ref",
        "locked": u"Locked",
    }

    def _patched_update(self):
        _original_update(self)
        for col in self.columns:
            label = _HEADERS.get(col.get("name"))
            if label:
                col["label"] = label

    DataGridWidget.update = _patched_update


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

    from senaite.core.schema.interimfields import IInterimField
    from senaite.core.schema.interimfields import InterimFields
    from senaite.core.schema.fields import DataGridRow
    from zope import schema as _schema
    from bika.lims import senaiteMessageFactory as _dx

    # Create a patched interface that extends IInterimField with formula and cross_referenceable
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
        cross_referenceable = _schema.Bool(
            title=_dx(
                u"label_interim_crossref",
                default=u"Cross-ref"
            ),
            required=False,
            default=False
        )
        locked = _schema.Bool(
            title=_dx(
                u"label_interim_locked",
                default=u"Locked"
            ),
            description=_dx(
                u"description_interim_locked",
                default=u"Value cannot be changed from the results entry form "
                        u"(for instrument-acquired data)"
            ),
            required=False,
            default=False
        )

    # Replace the value_type with new schema
    InterimFields.value_type = DataGridRow(schema=IInterimFieldPatched)

    _sys.stderr.write("maitux: IInterimFieldPatched names: %s\n"
                      % str(list(IInterimFieldPatched.names())))
    _sys.stderr.write("maitux: InterimFields.value_type updated\n")
    _sys.stderr.flush()

    # Patch DataGrid column header for cross_referenceable (Bool title="" → no per-cell label)
    _patch_datagrid_crossref_header()


# ==============================================================================
# FOLDERITEM PATCH — Map custom types to ReactJS components
# ==============================================================================

def _patch_folder_item():
    """Patch _folder_item_calculation to map list→multivalue, calculated→readonly."""
    from bika.lims.browser.analyses import view as analysis_view

    original_folderitem = analysis_view.AnalysesView._folder_item_calculation

    def patched_folderitem(self, analysis_brain, item):
        try:
            original_folderitem(self, analysis_brain, item)
        except Exception:
            import traceback, sys
            sys.stderr.write("maitux: folderitem crash for %s\n" % analysis_brain.get("id", "?"))
            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush()
            return

        interim_fields = item.get("interimfields", [])
        for idx, interim_field in enumerate(interim_fields):
            keyword = interim_field.get("keyword", "")
            result_type = interim_field.get("result_type", "")

            if result_type == "list":
                if keyword in item:
                    # Prefer raw value from interim_field (JSON string) over the
                    # formatted display value from item[keyword] which may have
                    # been processed by patched_get_formatted_interim into CJK
                    # unicode (e.g. u"甲醇, 乙酸乙酯"), causing str() to crash.
                    value = interim_field.get("value", "")
                    if not value:
                        value = item[keyword].get("value", "")
                    if value:
                        try:
                            # Python 2: str(u"\u4e2d\u6587") → UnicodeEncodeError
                            sval = value if isinstance(value, unicode) else str(value)
                            parsed = json.loads(sval)
                            if not isinstance(parsed, list):
                                value = json.dumps([sval])
                        except Exception:
                            # Already formatted display text — keep as-is
                            pass
                    item[keyword]["value"] = value
                    item[keyword]["result_type"] = "multivalue"
                    item[keyword]["_orig_result_type"] = "list"
                    if keyword in item.get("choices", {}):
                        del item["choices"][keyword]
                    # Also update the entry in interimfields list
                    interim_field["result_type"] = "multivalue"
                    interim_field["_orig_result_type"] = "list"

            elif result_type == "calculated":
                if keyword in item:
                    item[keyword]["result_type"] = "readonly"
                    item[keyword]["_orig_result_type"] = "calculated"
                    if keyword in item.get("choices", {}):
                        del item["choices"][keyword]
                    # Also update the entry in interimfields list
                    interim_field["result_type"] = "readonly"
                    interim_field["_orig_result_type"] = "calculated"

            elif result_type == "calculatedlist":
                if keyword in item:
                    # Parse and ensure valid JSON array for MultiValue display
                    value = item[keyword].get("value", "")
                    if value:
                        try:
                            parsed = json.loads(str(value))
                            if not isinstance(parsed, list):
                                value = json.dumps([str(value)])
                        except (ValueError, TypeError):
                            value = json.dumps([str(value)])
                    item[keyword]["value"] = value
                    item[keyword]["result_type"] = "multivalue"
                    item[keyword]["_orig_result_type"] = "calculatedlist"
                    if keyword in item.get("choices", {}):
                        del item["choices"][keyword]
                    interim_field["result_type"] = "multivalue"
                    interim_field["_orig_result_type"] = "calculatedlist"

    analysis_view.AnalysesView._folder_item_calculation = patched_folderitem


# ==============================================================================
# IS_MULTI_INTERIM PATCH — Treat "list" as multi-value
# ==============================================================================

def _patch_is_multi_interim():
    """Patch is_multi_interim to treat 'list' as a multi-value type.

    Only returns True for list type if the value is actually a JSON list,
    to avoid crashing api.to_list() on empty or plain-number values.
    """
    from bika.lims.browser.analyses import view as analysis_view

    original_is_multi = analysis_view.AnalysesView.is_multi_interim

    def patched_is_multi_interim(self, interim):
        if interim.get("result_type", "") == "list":
            raw = interim.get("value", "")
            if raw:
                try:
                    parsed = json.loads(str(raw))
                    if isinstance(parsed, list):
                        return True
                except (ValueError, TypeError):
                    pass
            return False
        return original_is_multi(self, interim)

    analysis_view.AnalysesView.is_multi_interim = patched_is_multi_interim


# ==============================================================================
# VALIDATOR PATCH — Normalize bytes/unicode in InterimFields keyword/title comparison
# ==============================================================================

# [PY2-UNICODE] Not a calculation feature -- see README.md.
def _patch_validator_interimfields_unicode():
    """Patch InterimFieldsValidator.__call__ to normalize bytes vs unicode.
    
    Python 2: when an AS has no Calculation reference and fields are entered
    manually via the form, submitted title values arrive as UTF-8 bytes.
    But Calculation-stored titles are unicode. '溶剂名称' != u'溶剂名称' in
    Python 2, causing spurious validation errors.
    """
    import sys as _sys
    _sys.stderr.write("maitux: patching InterimFieldsValidator for unicode safety\n")
    _sys.stderr.flush()

    from bika.lims.validators import InterimFieldsValidator
    from bika.lims import api as _api

    def _uni(v):
        if isinstance(v, str):
            try:
                return v.decode("utf-8")
            except UnicodeDecodeError:
                return v
        return v

    _original_call = InterimFieldsValidator.__call__

    def _patched_call(self, value, *args, **kwargs):
        instance = kwargs.get('instance')
        field = kwargs.get('field')
        if instance is None or field is None:
            return _original_call(self, value, *args, **kwargs)
        request = instance.REQUEST
        form = request.form
        fieldname = field.getName()
        interim_fields = form.get(fieldname, [])
        # Normalize all submitted interim_fields to unicode before validation
        for row in interim_fields:
            for k in row.keys():
                row[k] = _uni(row[k])
        value = _uni(value)
        return _original_call(self, value, *args, **kwargs)

    InterimFieldsValidator.__call__ = _patched_call
    _sys.stderr.write("maitux: InterimFieldsValidator unicode patch done\n")
    _sys.stderr.flush()


# ==============================================================================
# GET_FORMATTED_INTERIM PATCH — Display calculated values
# ==============================================================================

def _patch_get_formatted_interim():
    """Patch get_formatted_interim for 'calculated' and 'list' type display."""
    from bika.lims.browser.analyses import view as analysis_view

    original_formatted = analysis_view.AnalysesView.get_formatted_interim

    def patched_get_formatted_interim(self, interim):
        rt = interim.get("result_type", "")
        raw_value = interim.get("value", "") or ""

        if rt == "calculated":
            from bika.lims.browser.analyses.view import formatDecimalMark
            return formatDecimalMark(raw_value, self.dmk)

        # For list types (including those mapped to multivalue), avoid
        # formatDecimalMark which crashes on unicode (e.g. Chinese characters)
        if rt == "multivalue" and interim.get("_orig_result_type") == "list":
            try:
                import json
                arr = json.loads(str(raw_value))
                if isinstance(arr, list):
                    if arr and isinstance(arr[0], basestring):
                        return u", ".join([unicode(v) for v in arr])
            except Exception:
                pass

        # Handle raw "list" type before folder_item mapping
        if rt == "list":
            if not raw_value:
                return u""
            try:
                import json
                arr = json.loads(str(raw_value))
                if isinstance(arr, list):
                    if arr and isinstance(arr[0], basestring):
                        return u", ".join([unicode(v) for v in arr])
            except Exception:
                pass
            return raw_value

        # Handle "calculatedlist" type — format each number, newline-separated
        if rt == "calculatedlist" or (rt == "readonly" and interim.get("_orig_result_type") == "calculatedlist"):
            if not raw_value:
                return u""
            try:
                import json
                from bika.lims.browser.analyses.view import formatDecimalMark
                arr = json.loads(str(raw_value))
                if isinstance(arr, list):
                    formatted = []
                    for v in arr:
                        try:
                            formatted.append(formatDecimalMark(float(v), self.dmk))
                        except (ValueError, TypeError):
                            formatted.append(unicode(v))
                    return u"\n".join(formatted)
            except Exception:
                pass
            return raw_value

        return original_formatted(self, interim)

    analysis_view.AnalysesView.get_formatted_interim = patched_get_formatted_interim


# ==============================================================================
# FORMAT_INTERIM PATCH — unicode-safe interim rendering in printed reports
# [PY2-UNICODE] Not a calculation feature -- see README.md.
# ==============================================================================
#
# This is the report-side twin of _patch_get_formatted_interim above.  The
# listing view was fixed long ago; the report renderer goes through a different
# function that nobody had touched, so the same defect was still live there.
#
# bika.lims.utils.analysis.format_interim routes every interim whose
# result_type is not "string"/"text" through formatDecimalMark, and
# formatDecimalMark opens with
#
#     rawval = str(value)     # <-- outside its own try/except
#
# Our "list" and "calculatedlist" interims legitimately hold text: impurity
# names (未知杂质), solvent names (甲醇), the "—" placeholder.  api.to_list()
# json-decodes the stored array into *unicode* strings, so str() tries an ascii
# encode and the whole report dies with
#
#     UnicodeEncodeError: 'ascii' codec can't encode characters in position 0-3
#
# and no PDF is produced at all.  Measured on 2026-08-26: 23 such fields in
# MaiLIMS, 8 in InnoCare, 6 in Care.
#
# format_supsub, called a few lines further down for the unit, carries the same
# `str(text)` and breaks on any non-ascii unit such as "μg/mL".
#
# Behaviour of the replacement:
#   * decimal-mark substitution is kept, but only for values that really are
#     numeric (including the "< 2.1" / "> 2.1" forms core's own tests cover).
#     Applying it to text would corrupt names containing a dot.
#   * non-numeric values pass through as unicode text.  They are NOT
#     html-escaped here: results.pt renders formatted_value with tal:content,
#     not `structure`, so TAL escapes it and doing it twice would surface
#     literal &lt;br/&gt; in the PDF.
#   * the choices mapping is matched on unicode on both sides, otherwise a
#     CJK choice label silently renders as an empty cell instead of crashing.

_NUMERIC_RE = None


def _looks_numeric(text):
    """True for values formatDecimalMark was actually meant to handle."""
    global _NUMERIC_RE
    if _NUMERIC_RE is None:
        import re as _re
        # plain numbers, scientific notation, and the detection-limit forms
        # ("< 2.1", "> 2.1") that senaite.core's own tests pin down
        _NUMERIC_RE = _re.compile(
            r"^\s*[<>]?\s*[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?\s*$")
    return bool(_NUMERIC_RE.match(text))


def _format_decimal_safe(value, decimal_mark):
    """formatDecimalMark without the str(u"CJK") crash."""
    text = _safe_text(value)
    if not _looks_numeric(text):
        # a decimal-mark swap on free text would corrupt it (e.g. an impurity
        # name containing a dot), so leave it alone
        return text
    try:
        return _safe_text(decimal_mark).join(text.split(u"."))
    except Exception:
        return text


def _format_supsub_safe(unit):
    """format_supsub without the str(u"μg/mL") crash."""
    text = _safe_text(unit)
    try:
        text.encode("ascii")
    except UnicodeEncodeError:
        # non-ascii units carry no ^ / _ markup in practice; returning them
        # verbatim is better than losing the whole report
        return text
    try:
        from bika.lims.utils import format_supsub
        return format_supsub(text)
    except Exception:
        return text


def _patch_format_interim():
    """Replace format_interim with a Python 2 unicode-safe equivalent."""
    import sys as _sys
    from bika.lims import api
    from bika.lims.utils import formatTextResult
    from bika.lims.utils import analysis as analysis_utils

    def safe_format_interim(interim_field, html=True):
        separator = u"<br/>" if html else u", "
        result_type = interim_field.get("result_type", "")

        # copy to prevent persistent changes
        item = deepcopy(interim_field)

        value = item.get("value", "")
        values = filter(None, api.to_list(value))

        choices = item.get("choices")
        if choices:
            mapping = {}
            for chunk in _safe_text(choices).split(u"|"):
                chunk = chunk.strip()
                if u":" not in chunk:
                    continue
                # split once only: a label may legitimately contain a colon,
                # which made the original raise "too many values to unpack"
                key, text = chunk.split(u":", 1)
                mapping[key.strip()] = text.strip()
            texts = [mapping.get(_safe_text(v), u"") for v in values]
            values = filter(None, texts)

        elif result_type in ["string", "text"]:
            values = [formatTextResult(val, html) for val in values]

        else:
            setup = api.get_senaite_setup()
            decimal_mark = setup.getResultsDecimalMark()
            values = [_format_decimal_safe(val, decimal_mark)
                      for val in values]

        item["formatted_value"] = separator.join(
            [_safe_text(v) for v in values])

        unit = item.get("unit", "")
        item["formatted_unit"] = (
            _format_supsub_safe(unit) if html else _safe_text(unit))

        return item

    safe_format_interim._maitux_patched = True
    analysis_utils.format_interim = safe_format_interim

    # senaite.impress binds the name at module import time
    # ("from bika.lims.utils.analysis import format_interim"), so rebinding
    # the source module alone would leave the report path -- the only path
    # that actually crashes -- on the old function.
    rebound = ["bika.lims.utils.analysis"]
    impress_done = False
    try:
        from senaite.impress.analysisrequest import reportview
        reportview.format_interim = safe_format_interim
        rebound.append("senaite.impress...reportview")
        impress_done = True
    except Exception as exc:
        rebound.append("senaite.impress PENDING (%s)" % exc)

    _sys.stderr.write(
        "maitux: format_interim patched for unicode safety (%s)\n"
        % ", ".join(rebound))
    _sys.stderr.flush()
    return impress_done


def _patch_format_interim_deferred(event=None):
    """Retry the impress rebinding once every product is loaded.

    Same reasoning as _patch_listing_set_field_deferred: apply_patches() runs
    while this package is being imported, which on a cold start can be before
    senaite.impress is importable.  Without the retry the core module would be
    patched but the report path would silently keep the crashing function --
    the worst possible outcome, since that is the only path that fails.
    """
    _s = __import__("sys")
    try:
        from senaite.impress.analysisrequest import reportview
    except Exception as exc:
        _s.stderr.write(
            "maitux: deferred format_interim patch failed to import "
            "senaite.impress: %s\n" % exc)
        return
    if getattr(reportview.format_interim, "_maitux_patched", False):
        return   # the eager attempt already won
    from bika.lims.utils import analysis as analysis_utils
    reportview.format_interim = analysis_utils.format_interim
    _s.stderr.write(
        "maitux: format_interim rebound on senaite.impress (deferred)\n")
    _s.stderr.flush()


# ==============================================================================
# SET_INTERIM_VALUE PATCH — Normalize list + re-evaluate calculated
# ==============================================================================

# ==============================================================================
# LOCKED INTERIMS — Write protection for instrument-acquired data
# ==============================================================================
#
# An interim marked "locked" in the Calculation config must not be altered
# through the results entry form.  This is a data integrity control, so it is
# enforced on the *server*: rendering the widget read-only is cosmetic only and
# would be trivially bypassed by posting to the save endpoint directly.
#
# Two write paths exist and both are guarded:
#
#   setInterimValue(keyword, value)  the interactive path.  This is what
#                                    IDataManager.set() calls for every field
#                                    edited in a listing.  Locked keywords are
#                                    refused outright.
#   setInterimFields(interims)       the batch path, also reachable from the
#                                    Submit adapter via the `item_data` JSON
#                                    payload.  Stored values of locked fields
#                                    are restored, so a tampered payload cannot
#                                    overwrite captured data.
#
# The instrument importer legitimately needs to write these fields.  It should
# wrap its writes in `allow_locked_writes()`, which lifts the guard for the
# current thread only:
#
#     from maitux.calcenhance.patches import allow_locked_writes
#     with allow_locked_writes():
#         analysis.setInterimValue("peak_area", values)

import threading

_locked_writes = threading.local()


class allow_locked_writes(object):
    """Context manager lifting the locked-interim guard for this thread.

    Thread-local on purpose: Zope serves requests on multiple threads, and a
    plain module-level flag would open the guard for concurrent requests too.
    """

    def __enter__(self):
        depth = getattr(_locked_writes, "depth", 0)
        _locked_writes.depth = depth + 1
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        _locked_writes.depth = max(0, getattr(_locked_writes, "depth", 0) - 1)
        return False


def _locked_writes_allowed():
    return getattr(_locked_writes, "depth", 0) > 0


def _safe_text(value):
    """Coerce to unicode without the Python 2 str(u"CJK") crash."""
    if value is None:
        return u""
    if isinstance(value, unicode):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return unicode(value)


def _same_value(a, b):
    """Whether two stored interim values mean the same thing.

    Comparing the stored TEXT caused three separate defects, because
    the identity of these values is the parsed structure, not the bytes:

      * a locked interim whose stored form was the real character while
        the computed form was the ASCII escape ('["\\u2014"]' against
        '["---"]' with a real em dash) never compared equal, so
        `changed` stayed true on every pass and the evaluation chain
        recursed until the stack blew (ISSUE-016);
      * in Python 2 a str/unicode pair with identical characters
        compares unequal (with a UnicodeWarning), so an unchanged value
        looked changed and triggered needless re-evaluation, needless
        write-backs and needless audit snapshots;
      * '["2", "2"]' and '["2","2"]' differ only in whitespace.

    Numbers are compared as parsed, so 0 and 0.0 are the same value.
    Types are NOT coerced: the text "2" and the number 2 stay
    different, so the engine still gets to replace a string-typed
    result with a numeric one exactly once.

    Falls back to text comparison when either side is not JSON.
    """
    text_a, text_b = _safe_text(a), _safe_text(b)
    if text_a == text_b:
        return True
    try:
        parsed_a = json.loads(text_a)
        parsed_b = json.loads(text_b)
    except Exception:
        return False
    return parsed_a == parsed_b


def _lookup_key_omitted(value):
    """Whether a LOOKUP key argument means "this source has one row".

    The configured formulas spell it two ways and 32 of the 96 calls
    rely on it, so both stay valid:

        LOOKUP("imp_sys_suit", "F_main", "imp_main_name", "")
        LOOKUP("imp_sys_suit", "imp_main_name", "imp_main_name", 0)
    """
    if value is None:
        return True
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, long, float)):
        return value == 0
    if isinstance(value, basestring):
        return value.strip() in ("", "0")
    return False


def _coalesce_pick(values):
    """First present value, plus the present values that disagree with it.

    Returns (chosen, disagreeing).  All-missing yields (_MISSING, []).
    Presence is the missing-value rule from ISSUE-017: the sentinel,
    the "---" text, None and "" all count as absent.
    """
    present = []
    for value in values:
        if value is None:
            continue
        if _is_missing(value):
            continue
        if isinstance(value, basestring) and not value.strip():
            continue
        present.append(value)
    if not present:
        return _MISSING, []
    chosen = present[0]
    disagreeing = [v for v in present[1:] if not _same_value(v, chosen)]
    return chosen, disagreeing


def _same_value_map(before, after):
    """Whether two {keyword: value} maps mean the same thing."""
    if set(before) != set(after):
        return False
    for keyword in before:
        if not _same_value(before[keyword], after[keyword]):
            return False
    return True


def _is_locked(interim):
    """Whether an interim dict carries the locked flag.

    The value arrives as a real bool from the Dexterity schema but as a string
    from the Archetypes subfield and from XLSX import, so accept both.
    """
    flag = interim.get("locked", False)
    if isinstance(flag, bool):
        return flag
    return _safe_text(flag).strip().lower() in ("true", "1", "yes", "on", "x")


def _find_interim(analysis, keyword):
    try:
        for interim in analysis.getInterimFields() or []:
            if interim.get("keyword") == keyword:
                return interim
    except Exception:
        pass
    return None


def _preserve_locked_interims(analysis, new_interims):
    """Restore the stored value of every locked interim in `new_interims`.

    A field with no captured value yet is left alone, so the first write (the
    instrument import) goes through even outside allow_locked_writes().
    """
    from bika.lims import logger

    try:
        stored = analysis.getInterimFields() or []
    except Exception:
        return new_interims

    stored_by_keyword = {}
    for interim in stored:
        keyword = interim.get("keyword")
        if keyword:
            stored_by_keyword[keyword] = interim

    blocked = []
    for interim in new_interims:
        keyword = interim.get("keyword")
        if not keyword:
            continue
        old = stored_by_keyword.get(keyword)
        if old is None:
            # Not stored yet: this is the initial write
            continue
        if not (_is_locked(old) or _is_locked(interim)):
            continue
        old_value = old.get("value", "")
        if old_value in (None, ""):
            # Nothing captured yet, let the first value in
            continue
        if _same_value(interim.get("value", ""), old_value):
            continue
        interim["value"] = old_value
        blocked.append(keyword)

    if blocked:
        logger.warn(
            "maitux.calcenhance: refused to overwrite locked interim(s) %s on "
            "%s" % (", ".join(blocked), getattr(analysis, "id", "?")))

    return new_interims


def _patch_set_interim_value():
    """Patch setInterimValue:
    - Refuses writes to locked interims
    - Normalizes list-type values to JSON arrays
    - After saving, re-evaluates all Calculated and CalculatedList interims
    """

    def patched_setInterimValue(self, keyword, value):
        # Locked interims are not editable from the results entry form
        if not _locked_writes_allowed():
            interim = _find_interim(self, keyword)
            if interim is not None and _is_locked(interim):
                stored = interim.get("value", "")
                if stored not in (None, ""):
                    from bika.lims import logger
                    logger.warn(
                        "maitux.calcenhance: refused write to locked interim "
                        "'%s' on %s" % (keyword, getattr(self, "id", "?")))
                    return

        # Pre-process value (normalize list to JSON array)
        value = _preprocess_value(self, keyword, value)

        # --- Original save logic (inline) ---
        import json as _j
        # string_types may not exist in newer senaite.core; fall back
        try:
            from bika.lims.utils import string_types
        except ImportError:
            string_types = basestring
        if value is None:
            value = ""
        elif isinstance(value, string_types):
            value = value.strip()
        elif isinstance(value, (list, tuple, set, dict)):
            value = _j.dumps(value)

        # deepcopy is required, not cosmetic: ObjectField.get() hands out the
        # persistent list itself (Products/Archetypes/Field.py, ObjectField.get
        # -> getStorage().get()), so editing these dicts writes straight into
        # the stored value.  setInterimFields() would then snapshot the
        # already-modified data as its "before" state and conclude nothing
        # changed, which silently disables the LOOKUP re-calculation of
        # dependent analyses.  senaite.core guards the same way -- see the
        # deepcopy in AnalysesView._folder_item_calculation.
        interims = deepcopy(self.getInterimFields())
        for interim in interims:
            if interim.get("keyword") == keyword:
                interim["value"] = str(value)
        self.setInterimFields(interims)
        # --- End original save logic ---

        # Re-evaluate every computed interim, in definition order
        _evaluate_interims_ordered(self)

    try:
        import sys as _s2
        # Try both possible locations for AbstractBaseAnalysis
        klass = None
        try:
            from bika.lims.content.abstractanalysis import AbstractAnalysis as klass
            if not hasattr(klass, "setInterimValue"):
                klass = None
        except Exception:
            klass = None
        if klass is None:
            from bika.lims.content.abstractbaseanalysis import AbstractBaseAnalysis as klass
        _s2.stderr.write("maitux: patching setInterimValue on %s.%s\n"
                        % (klass.__module__, klass.__name__))
        _s2.stderr.write("maitux: has setInterimValue? %s\n"
                        % str(hasattr(klass, "setInterimValue")))
        setattr(klass, "setInterimValue", patched_setInterimValue)
        _s2.stderr.write("maitux: setInterimValue patch applied OK\n")
        _s2.stderr.flush()
    except Exception as _e:
        _s = __import__("sys")
        _s.stderr.write("maitux: setInterimValue patch FAILED: %s\n" % str(_e))
        _s.stderr.flush()


def _unecho_list_value(val):
    """Undo a widget echo: every row holding the entire array.

    The listing's MultiValue component (senaite.app.listing, upstream)
    seeds its React state from props in the constructor only -- there
    is no componentDidUpdate/getDerivedStateFromProps -- so a reused
    component instance keeps a stale value across re-renders and its
    inputs can end up each holding the whole JSON array.  Saving that
    stores an array whose every element is the previous array: one
    extra layer per save.  The audit trail of BR-0006/std1_peak_area
    shows exactly that -- 1 layer at 07:18:16, 2 at 07:18:23, 3 a
    minute later.

    Signature: two or more elements, all identical, each parsing as a
    JSON array.  Real results never look like that -- every row would
    have to carry the same JSON array text.

    Returns the inner array, so the ROW COUNT is preserved.  Flattening
    by concatenation doubles the row count instead, the sibling arrays
    then no longer match, and the engine's length gate skips every
    dependent field without writing anything -- a stale value stays on
    screen, which is worse than visible nesting.
    """
    import ast as _ue_ast

    def _parse_list(text):
        """Parse a JSON array or a Python-repr array; None otherwise."""
        for parse in (json.loads, _ue_ast.literal_eval):
            try:
                out = parse(text)
            except Exception:
                continue
            if isinstance(out, list):
                return out
        return None

    for _ in range(6):        # bounded; layers seen in the wild are <= 3
        arr = _parse_list(_safe_text(val))
        if arr is None or len(arr) < 2:
            return val
        first = arr[0]
        if not isinstance(first, basestring):
            return val
        if any(item != first for item in arr):
            return val
        # Both spellings occur: the form posts JSON, while values that
        # went through a Python repr somewhere arrive as "[u'..']".
        if _parse_list(first) is None:
            return val
        from bika.lims import logger as _ue_logger
        _ue_logger.warn(
            "maitux.calcenhance: list value had %d identical rows each "
            "holding the whole array (MultiValue echo); kept the inner "
            "value" % len(arr))
        val = first
    return val


def _normalize_list_value(val):
    """Normalize a list-type interim value to a proper JSON array string.

    Repairs one encoding layer per pass, so loop until the value settles:
    a value that went through several bad round trips (observed on
    /Care imp_linearity.imp_name, three layers deep) would otherwise need
    one save per layer before it read correctly.
    """
    for _ in range(8):
        out = _normalize_list_value_once(val)
        if out == val:
            return out
        val = out
    return val


def _normalize_list_value_once(val):
    """One normalisation pass.  See _normalize_list_value."""
    if not val:
        return val

    # Repair a MultiValue echo before anything else, so the row count is
    # preserved instead of being multiplied by the flattening below.
    val = _unecho_list_value(val)

    # If it's not a string, json.dumps it
    if not isinstance(val, basestring):
        try:
            return json.dumps(list(val))
        except Exception:
            return val

    # Python 2: use unicode directly to avoid UnicodeEncodeError with CJK
    if isinstance(val, unicode):
        sval = val
    else:
        sval = str(val)

    # Already a valid JSON array?
    try:
        parsed = json.loads(sval)
        if isinstance(parsed, list):
            # Check if any element is a Python-repr string that nests another list
            # (handles triple-encoded values like ["[u'\\u7532...']"])
            import ast
            items = []
            for item in parsed:
                if isinstance(item, basestring):
                    # Only try ast.literal_eval on byte strings (Python repr format)
                    # Unicode strings are already proper values, skip
                    try:
                        item_str = item if isinstance(item, unicode) else str(item)
                        sub = ast.literal_eval(item_str)
                        # A Python-repr encoded array legitimately
                        # holds several values in one JSON element, so
                        # flattening it here is the repair, and the row
                        # count is SUPPOSED to grow.  (Restricting this
                        # to single-element sub-lists stopped the
                        # repair and the nesting piled up instead.)
                        # The widget-echo case, where growing the row
                        # count would be wrong, is caught earlier and
                        # length-preservingly by _unecho_list_value.
                        if isinstance(sub, list):
                            items.extend(sub)
                            continue
                    except Exception:
                        pass
                items.append(item)
            if items != parsed:
                return json.dumps(items)
            return json.dumps(parsed)
    except Exception:
        pass

    # Python repr format? (e.g., "[u'\\u7532\\u9187', ...]")
    try:
        import ast
        parsed = ast.literal_eval(sval)
        if isinstance(parsed, list):
            items = []
            for v in parsed:
                items.append(v if isinstance(v, unicode) else v)
            return json.dumps(items)
    except Exception:
        pass

    # Split by newlines
    parts = [v.strip() for v in sval.replace("\r\n", "\n").replace("|", "\n").split("\n") if v.strip()]
    if not parts:
        parts = [v.strip() for v in sval.split(",") if v.strip()]
    if parts:
        return json.dumps(parts, ensure_ascii=False)

    return val


def _patch_set_interim_fields():
    """Patch setInterimFields to normalize list values + evaluate calculated.

    This is the primary entry point when an Analysis is first saved —
    setInterimFields is called with all interims at once. setInterimValue
    (also patched) is only called for individual field edits.

    setInterimFields is auto-generated by Archetypes ClassGen from the
    InterimFields field definition, so it lives in __dict__ not via
    explicit class definition.
    """

    try:
        from bika.lims.content.analysis import Analysis
    except Exception:
        return

    if "setInterimFields" not in Analysis.__dict__:
        _s = __import__("sys")
        _s.stderr.write("maitux: setInterimFields not found in Analysis.__dict__, skip\n")
        return

    original = Analysis.__dict__["setInterimFields"]

    def patched_setInterimFields(self, interims):
        # Snapshot current cross-referenceable field values, so we can detect
        # changes and propagate LOOKUP re-evaluation to dependent siblings.
        before = {}
        try:
            for _i in self.getInterimFields():
                if _i.get("cross_referenceable"):
                    before[_i.get("keyword")] = _i.get("value")
        except Exception:
            before = {}

        # Restore the stored value of locked interims.  This is the batch
        # write path and is also what the native Submit adapter feeds from the
        # `item_data` form payload, so a tampered payload must not get through.
        if not _locked_writes_allowed():
            interims = _preserve_locked_interims(self, interims)

        # Normalize list-type values before saving
        for i in interims:
            rt = i.get("result_type", "")
            if rt == "list":
                val = i.get("value", "")
                if val:
                    i["value"] = _normalize_list_value(val)

        # Call original save
        original(self, interims)

        # Evaluate calculated interims, bounded against non-convergence
        # (see _MAX_EVAL_DEPTH).
        _depth = getattr(_eval_depth_local, "depth", 0)
        if _depth >= _MAX_EVAL_DEPTH:
            from bika.lims import logger as _depth_logger
            _depth_logger.warn(
                "maitux.calcenhance: interim evaluation did not converge "
                "after %d passes on %s -- stopping.  A locked computed "
                "interim whose stored value differs from the computed one "
                "will do this." % (_depth, getattr(self, "id", "?")))
        else:
            _eval_depth_local.depth = _depth + 1
            try:
                _evaluate_interims_ordered(self)
            finally:
                _eval_depth_local.depth = _depth

        # If any cross-referenceable field actually changed, re-evaluate the
        # sibling analyses whose LOOKUP() references this AS.
        cross_ref_changed = False
        for i in interims:
            if not i.get("cross_referenceable"):
                continue
            if not _same_value(before.get(i.get("keyword")),
                               i.get("value")):
                cross_ref_changed = True
                break

        _local = _get_propagation_local()
        is_top = getattr(_local, "visited", None) is None
        try:
            if cross_ref_changed:
                _propagate_lookup_recalc(self)
        finally:
            if is_top:
                _finish_propagation()

    setattr(Analysis, "setInterimFields", patched_setInterimFields)
    _s = __import__("sys")
    _s.stderr.write("maitux: setInterimFields patch applied OK\n")
    _s.stderr.flush()


def _patch_calculate_result():
    """Patch native AbstractAnalysis.calculateResult to skip analyses whose
    main formula references a list / calculatedlist interim holding a JSON
    array.

    SENAITE core wraps non-floatable interim values as '"{}"'.format(value).
    For a list interim stored as a JSON array (e.g. '["11"]') that yields
    '"["11"]"', which crashes the second eval() inside calculateResult with a
    SyntaxError.  Those analyses are already recalculated element-wise by
    _evaluate_calculated_interims / _evaluate_calculatedlist_interims (invoked
    from setInterimValue / setInterimFields), so the native scalar calculation
    is meaningless for them and must be skipped.

    Scalar formulas (e.g. AS-1 '[F_main]') that merely *coexist* with list
    interims but do not reference them are left untouched.
    """
    try:
        from bika.lims.content.abstractanalysis import AbstractAnalysis
    except Exception:
        return

    if "calculateResult" not in AbstractAnalysis.__dict__:
        return

    original = AbstractAnalysis.__dict__["calculateResult"]

    import re as _cr_re
    _CR_TOKEN = _cr_re.compile(r'\[([A-Za-z_]\w*)\]')

    def _is_json_array(val):
        if val is None or val == "":
            return False
        try:
            if isinstance(val, unicode):
                sval = val
            elif isinstance(val, str):
                sval = val.decode("utf-8", "replace")
            else:
                sval = unicode(val)
            return isinstance(json.loads(sval), list)
        except Exception:
            return False

    def patched_calculateResult(self, override=False, cascade=False):
        try:
            formula = self.getCalculationFormula() or ""
            if formula:
                list_kws = set()
                for im in self.getInterimFields() or []:
                    kw = im.get("keyword", "")
                    rt = im.get("result_type", "")
                    if (kw and rt in ("list", "calculatedlist")
                            and _is_json_array(im.get("value", ""))):
                        list_kws.add(kw)
                if list_kws:
                    for m in _CR_TOKEN.finditer(formula):
                        if m.group(1) in list_kws:
                            return False
        except Exception:
            pass
        return original(self, override, cascade)

    setattr(AbstractAnalysis, "calculateResult", patched_calculateResult)
    _s = __import__("sys")
    _s.stderr.write("maitux: calculateResult patch applied OK\n")
    _s.stderr.flush()


def _preprocess_value(self, keyword, value):
    """Normalize list-type values to JSON array format.

    The raw array is preserved as-is (not auto-averaged). Step 2 of
    _evaluate_calculated_interims handles averaging when Calculated
    formulas reference List values. This keeps the raw data available
    for CalculatedList element-wise pairing.
    """
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

    # Validate and normalize to a JSON array string (no averaging)
    try:
        arr = json.loads(_safe_text(value))
        if isinstance(arr, list):
            # Keep the original JSON array, but undo a MultiValue echo
            # first: this path (setInterimValue) is what both the
            # results form and the instrument importer go through.
            return _unecho_list_value(value)
    except (ValueError, TypeError):
        pass

    # Fallback: parse comma/newline/pipe separated values → JSON array
    parts = [v.strip() for v in str(value).replace(
        "\r\n", "\n").replace("|", "\n").split("\n") if v.strip()]
    if not parts:
        parts = [v.strip() for v in str(value).split(",") if v.strip()]
    if parts:
        return json.dumps(parts)

    return value


# ==============================================================================
# CROSS-ANALYSIS LOOKUP — Allow referencing interim fields from sibling analyses
# ==============================================================================

def _sample_tree_analyses(analysis):
    """Return every analysis of the sample this one belongs to, partitions
    included.

    Partitioning does not nest analyses: create_partition() builds a brand new
    AnalysisRequest linked through ParentAnalysisRequest and *moves* the chosen
    analyses into it, removing them from the primary.  Walking the container
    (aq_parent.objectValues) therefore only ever sees the analyses of one
    partition, which breaks LOOKUP as soon as the interdependent tests are
    split across partitions -- the very reason partitions are created.

    So resolve the root sample first, then ask it for its analyses:
    AnalysisRequest.getAnalyses() queries the catalog on `getAncestorsUIDs`,
    and an analysis indexes its whole ancestor chain, so querying from the root
    yields the root's own analyses plus those of every descendant partition.

    Note this is deliberately wider than the native dependency walk, which
    starts from `analysis.getRequest()` and therefore cannot see sibling
    partitions either.  "One sample" is what a lab means by it, partitions
    included.
    """
    request = None
    getter = getattr(analysis, "getRequest", None)
    if callable(getter):
        try:
            request = getter()
        except Exception:
            request = None
    if request is None:
        request = getattr(analysis, "aq_parent", None)
    if request is None:
        return []

    # Climb to the root sample; getAncestors() returns [parent, ..., root]
    root = request
    try:
        ancestors = request.getAncestors(all_ancestors=True)
        if ancestors:
            root = ancestors[-1]
    except Exception:
        root = request

    try:
        return root.getAnalyses(full_objects=True)
    except Exception:
        # Reference/duplicate analyses live in a worksheet, not in a sample
        try:
            return request.objectValues("Analysis")
        except Exception:
            return []


def _collect_cross_referenceable_data(analysis):
    """Collect cross-referenceable interim field values from sibling analyses.

    Returns a dict: {service_kw: {field_kw: value}}
    - For list/calculatedlist fields, value is the raw array (list)
    - For scalar fields, value is a float or string

    Only reads fields with cross_referenceable=True.
    Scope is the whole sample tree (see _sample_tree_analyses), so a test on
    one partition can read a reference standard measured on another.
    """
    import json as _jj
    sibling_data = {}
    siblings = _sample_tree_analyses(analysis)

    for sibling in siblings:
        try:
            if sibling.UID() == analysis.UID():
                continue
            svc = sibling.getAnalysisService()
            svc_kw = svc.getKeyword() if svc else ""
            if not svc_kw:
                continue
            interims = sibling.getInterimFields()
            for i in interims:
                if not i.get("cross_referenceable"):
                    continue
                kw = i.get("keyword", "")
                if not kw:
                    continue
                val = i.get("value", "")
                rt = i.get("result_type", "")
                if rt in ("list", "calculatedlist") and not val:
                    # An array-typed field with nothing captured yet
                    # must stay an ARRAY.  Falling through to the
                    # scalar branch stored it as "", and LOOKUP then
                    # handed that "" back as if it were a result -- a
                    # blank cell indistinguishable from a failed
                    # calculation.  An empty list makes LOOKUP raise
                    # instead, so the row shows the "---" placeholder
                    # and the screen says "source not entered yet".
                    if svc_kw not in sibling_data:
                        sibling_data[svc_kw] = {}
                    sibling_data[svc_kw][kw] = []
                    continue
                if rt in ("list", "calculatedlist") and val:
                    try:
                        arr = _jj.loads(str(val))
                        if isinstance(arr, list):
                            # Convert floatable string elements to float
                            # (frontend MultiValue submits text inputs → JSON strings)
                            import bika.lims.api as _api_ccr
                            typed = []
                            for v in arr:
                                try:
                                    if isinstance(v, (int, float)):
                                        typed.append(float(v))
                                    elif isinstance(v, basestring) and _api_ccr.is_floatable(v):
                                        typed.append(float(v))
                                    else:
                                        typed.append(v)
                                except Exception:
                                    typed.append(v)
                            if svc_kw not in sibling_data:
                                sibling_data[svc_kw] = {}
                            sibling_data[svc_kw][kw] = typed
                    except Exception:
                        pass
                else:
                    try:
                        import bika.lims.api as _api
                        if _api.is_floatable(val):
                            scalar = float(val)
                        else:
                            scalar = str(val) if val else ""
                    except Exception:
                        scalar = str(val) if val else ""
                    if svc_kw not in sibling_data:
                        sibling_data[svc_kw] = {}
                    sibling_data[svc_kw][kw] = scalar
        except Exception:
            pass

    return sibling_data


# Method-B "key not found" placeholder.  Preserved as a string element through
# calculatedlist arithmetic so unknown-peak rows keep their position in the
# JSON arrays (instead of being dropped and misaligning the review table).
_PLACEHOLDER = u"---"


# Re-entrancy bound for the interim evaluation chain.  Evaluation calls
# setInterimFields again whenever a value changed, which re-enters
# evaluation; dependency chains settle in one or two extra passes.  A value
# that can never be stored -- a locked computed interim whose stored form
# differs from the computed one -- keeps `changed` true on EVERY pass, and
# the chain then recursed until the stack blew (RuntimeError: maximum
# recursion depth exceeded), which made the object impossible to create.
# Bounding the depth breaks that without forbidding legitimate re-entry.
_MAX_EVAL_DEPTH = 8
_eval_depth_local = threading.local()

# How many front-to-back sweeps the ordered driver will run.  One is
# enough when the field order satisfies the dependencies; a second is
# needed only by an analysis whose stored order does not, and it is
# logged when that happens (see _evaluate_interims_ordered).
_MAX_ORDER_SWEEPS = 3


# --- Missing-value semantics -----------------------------------------------
#
#   aggregate functions SKIP missing members:
#       max(5.0, ---) == 5.0      avg(3, ---, 5) == 4
#       nothing left              -> "---"   (never 0)
#   binary operators PROPAGATE, they never invent an identity element:
#       5.0 - --- == "---"        2 + --- == "---"
#
# An operator needs its operand: a missing one means "cannot be computed",
# not "equals zero".  A two-method difference where one method has no
# result must read "---", not the value of the other method.
#
# Python 2 makes propagation the dangerous case, because none of these
# raise -- they quietly produce a plausible wrong answer:
#       2 * u"---"       == u"------"    (string repetition)
#       u"---" + u"---"  == u"------"
#       5.0 > u"---"     is False        (numbers sort before strings)
#       min(5.0, u"---") == 5.0
# Binding the placeholder to a sentinel instead makes every operator
# raise, and the caller turns that into "---".

class _Missing(object):
    """Stands in for the "---" placeholder while a formula is evaluated."""

    def _refuse(self, *args):
        raise TypeError("missing value has no arithmetic")

    __add__ = __radd__ = __sub__ = __rsub__ = _refuse
    __mul__ = __rmul__ = __mod__ = __rmod__ = _refuse
    __div__ = __rdiv__ = __truediv__ = __rtruediv__ = _refuse
    __floordiv__ = __rfloordiv__ = __pow__ = __rpow__ = _refuse
    __neg__ = __pos__ = __abs__ = _refuse
    __lt__ = __le__ = __gt__ = __ge__ = _refuse
    __int__ = __float__ = __long__ = _refuse

    def __eq__(self, other):
        return isinstance(other, _Missing)

    def __ne__(self, other):
        return not isinstance(other, _Missing)

    def __hash__(self):
        return hash(_PLACEHOLDER)

    def __repr__(self):
        return "MISSING"


_MISSING = _Missing()


def _is_missing(value):
    """Whether a value means "no result" -- the sentinel or the "---" text."""
    if isinstance(value, _Missing):
        return True
    try:
        return _safe_text(value) == _PLACEHOLDER
    except Exception:
        return False


def _present(values):
    """Aggregate helper: the members that are actually present."""
    if not isinstance(values, (list, tuple)):
        values = [values]
    return [v for v in values if not _is_missing(v)]


def _agg_args(args):
    """Accept both max(a, b) and max([a, b]) spellings."""
    if len(args) == 1 and isinstance(args[0], (list, tuple)):
        return _present(args[0])
    return _present(list(args))


def _skip_min(*args):
    vals = _agg_args(args)
    return min(vals) if vals else _MISSING


def _skip_max(*args):
    vals = _agg_args(args)
    return max(vals) if vals else _MISSING


def _skip_sum(*args):
    vals = _agg_args(args)
    return sum(vals) if vals else _MISSING


def _skip_avg(*args):
    vals = _agg_args(args)
    return sum(vals) / float(len(vals)) if vals else _MISSING


def _skip_stdev(*args):
    """Sample standard deviation, missing members skipped.

    Fewer than two present values cannot yield a spread.  This used to
    return 0.0, which reads as "perfectly reproducible" -- the most
    misleading answer available for a validation report.
    """
    vals = _agg_args(args)
    if len(vals) < 2:
        return _MISSING
    mean = sum(vals) / float(len(vals))
    import math as _sd_math
    return _sd_math.sqrt(
        sum((v - mean) ** 2 for v in vals) / (len(vals) - 1))


def _make_lookup(sibling_data):
    """Create a LOOKUP function bound to cross-referenceable sibling data.

    Usage in formula:
        LOOKUP("ServiceKeyword", "TargetField", "KeyField", key_value)

    Example:
        LOOKUP("对照品测定", "F", "溶剂名称", [溶剂名称])
        → finds "甲醇" in 溶剂名称 array → returns F[甲醇's index]

    The function searches sibling_data for the AnalysisService with keyword
    'source_kw', then finds the matching index in the key array and returns
    the corresponding value from the target array.
    """
    _NO_DEFAULT = object()

    def lookup(source_kw, target_kw, key_kw, key_val, default=_NO_DEFAULT):
        if not isinstance(source_kw, basestring):
            raise TypeError("LOOKUP source_kw must be a string")
        if not isinstance(target_kw, basestring):
            raise TypeError("LOOKUP target_kw must be a string")
        if not isinstance(key_kw, basestring):
            raise TypeError("LOOKUP key_kw must be a string")

        if source_kw not in sibling_data:
            raise KeyError(
                "LOOKUP: source service '%s' not found or has no "
                "cross-referenceable fields" % source_kw)

        data = sibling_data[source_kw]
        key_arr = data.get(key_kw)
        target_arr = data.get(target_kw)

        if key_arr is None:
            raise KeyError(
                "LOOKUP: key field '%s' not found in '%s'" % (key_kw, source_kw))
        if target_arr is None:
            raise KeyError(
                "LOOKUP: target field '%s' not found in '%s'" % (target_kw, source_kw))

        # A source field that has not been captured yet must not read
        # as a value.  Returning "" verbatim made "source not entered"
        # look exactly like a real blank result; raising lets the
        # callers emit the "---" placeholder instead.
        if isinstance(target_arr, list):
            if not target_arr:
                raise KeyError(
                    "LOOKUP: target field '%s' of '%s' has no data "
                    "yet" % (target_kw, source_kw))
        elif target_arr in (None, ""):
            raise KeyError(
                "LOOKUP: target field '%s' of '%s' has no data yet"
                % (target_kw, source_kw))
        else:
            # The source holds ONE row.  Returning it regardless of the
            # key meant an impurity row got handed the main component's
            # value -- a plausible wrong number, which is worse than a
            # blank.  So: an omitted key still means "give me the one
            # row" (32 configured calls spell that as "" or 0), but a
            # real key has to match.
            if _lookup_key_omitted(key_val):
                return target_arr
            if key_arr is None or key_arr == "":
                # No key column to match against; the old behaviour is
                # the only one available.
                return target_arr
            # Present the one-row source as a single-element column and
            # let the matching below run unchanged -- it already covers
            # both the element-wise and the scalar spellings.
            target_arr = [target_arr]
            if not isinstance(key_arr, list):
                key_arr = [key_arr]

        # Same for the key column: an empty key array can never match,
        # and reporting that as "" would hide it.
        if isinstance(key_arr, list):
            if not key_arr:
                raise KeyError(
                    "LOOKUP: key field '%s' of '%s' has no data "
                    "yet" % (key_kw, source_kw))
        elif key_arr in (None, ""):
            raise KeyError(
                "LOOKUP: key field '%s' of '%s' has no data yet"
                % (key_kw, source_kw))

        # --- Element-wise lookup: parse key_val as JSON array ---
        import json as _lookup_json
        key_values = None

        # 1) key_val is already a Python list (from calculatedlist eval)
        if isinstance(key_val, list):
            key_values = key_val
        # 2) key_val is a JSON array string (from [keyword] substitution)
        elif isinstance(key_val, basestring):
            try:
                parsed = _lookup_json.loads(str(key_val))
                if isinstance(parsed, list):
                    key_values = parsed
            except Exception:
                pass

        # Python 2 safe str helper — str(u"\u4e2d\u6587") crashes with UnicodeEncodeError
        def _safe_str(v):
            if v is None:
                return u""
            if isinstance(v, unicode):
                return v
            if isinstance(v, str):
                return v.decode("utf-8", "replace")
            return unicode(v)

        if key_values is not None:
            # Element-wise lookup: match each key, return array
            str_key_arr = [_safe_str(v) for v in key_arr]
            results = []
            for kv in key_values:
                sv = _safe_str(kv)
                try:
                    idx = str_key_arr.index(sv)
                    results.append(target_arr[idx])
                except ValueError:
                    if default is not _NO_DEFAULT:
                        results.append(default)
                    else:
                        raise KeyError(
                            u"LOOKUP: key '%s' not found in '%s' array of '%s'"
                            % (sv, key_kw, source_kw))
            return results

        # --- Scalar lookup (backward compat) ---
        key_val = _safe_str(key_val)

        # If key is also scalar, index 0
        if not isinstance(key_arr, list):
            if len(target_arr) > 0:
                return target_arr[0]
            raise IndexError("LOOKUP: target array is empty")

        # Array-to-array lookup by name
        str_key_arr = [_safe_str(v) for v in key_arr]
        try:
            idx = str_key_arr.index(key_val)
            return target_arr[idx]
        except ValueError:
            if default is not _NO_DEFAULT:
                return default
            raise KeyError(
                u"LOOKUP: key '%s' not found in '%s' array of '%s'"
                % (key_val, key_kw, source_kw))

    return lookup


# ==============================================================================
# LOOKUP DEPENDENCY PROPAGATION — re-evaluate siblings that reference this AS
# ==============================================================================

import re as _lookup_re
_LOOKUP_SRC_RE = _lookup_re.compile(r'LOOKUP\s*\(\s*["\']([^"\']+)["\']')

_calc_propagation_local = None  # threading.local, lazily created


def _get_propagation_local():
    global _calc_propagation_local
    if _calc_propagation_local is None:
        import threading as _threading
        _calc_propagation_local = _threading.local()
    return _calc_propagation_local


def _extract_lookup_sources(formula):
    """Return the set of source AS keywords referenced by LOOKUP() calls.

    Only the first (string literal) argument of each LOOKUP is captured; that
    argument is the source Analysis Service keyword.
    """
    if not formula:
        return set()
    return set(_LOOKUP_SRC_RE.findall(formula))


def _is_dead_analysis(analysis):
    """Whether an analysis must be skipped when propagating a recalculation.

    Mirrors the filter the native dependency walk applies in
    bika.lims.api.analysis.get_dependents(): retracted, rejected and retested
    analyses are superseded records and must keep the result they were closed
    with.  Recalculating them would rewrite history.

    Note this deliberately does NOT skip submitted or verified analyses: the
    native recalculation does not either, and skipping them would leave the
    sample internally inconsistent (a changed reference standard with sample
    results still derived from the old one).
    """
    try:
        from bika.lims.api.analysis import is_rejected
        from bika.lims.api.analysis import is_retested
        from bika.lims.api.analysis import is_retracted
    except ImportError:
        return False
    try:
        return bool(is_retracted(analysis) or is_rejected(analysis)
                    or is_retested(analysis))
    except Exception:
        return False


def _dependent_sibling_analyses(analysis):
    """Return sibling analyses whose LOOKUP() directly references this AS.

    Direct references only (no transitive closure).  Handles both Calculated
    and CalculatedList formulas, since both store the formula on the interim
    field dict.

    Scope is the whole sample tree, partitions included (see
    _sample_tree_analyses), so editing a reference standard on one partition
    re-evaluates the tests that LOOKUP it from another.
    """
    dependents = []
    siblings = _sample_tree_analyses(analysis)

    try:
        svc = analysis.getAnalysisService()
        own_kw = svc.getKeyword() if svc else ""
    except Exception:
        own_kw = ""
    if not own_kw:
        return dependents

    for sibling in siblings:
        try:
            if sibling.UID() == analysis.UID():
                continue
            if _is_dead_analysis(sibling):
                continue
            for interim in sibling.getInterimFields():
                formula = interim.get("formula", "") or ""
                if formula and own_kw in _extract_lookup_sources(formula):
                    dependents.append(sibling)
                    break
        except Exception:
            continue
    return dependents


def _interim_value_map(analysis):
    """{keyword: text value} of an analysis' interims.

    Used to tell whether propagation actually changed anything.  The
    values go through _safe_text so a str/unicode difference alone is
    not mistaken for a change (that mismatch is what turned an
    unrelated locked-interim write into an infinite recalculation).
    """
    try:
        interims = analysis.getInterimFields() or []
    except Exception:
        return {}
    out = {}
    for interim in interims:
        keyword = interim.get("keyword")
        if keyword:
            out[keyword] = _safe_text(interim.get("value", ""))
    return out


# How many propagated siblings one thread will remember before it stops
# recording.  A save touches a handful; anything near this is a batch
# import, which never asks for the list.
_MAX_PROPAGATION_RECORD = 256


def _record_propagated_sibling(sibling):
    """Remember a sibling that propagation actually changed.

    The listing's save endpoint re-renders only the rows it is handed
    back: senaite.app.listing ajax.ajax_set_fields narrows
    contentFilter["UID"] to whatever set_field reported, and that set
    comes from SENAITE's declared dependency graph -- a Calculation's
    main Formula and the DependentServices derived from it.

    A LOOKUP() lives in an *interim* formula and names its source with
    a string literal, so neither of those two places mentions it and
    getDependents() comes back empty.  Editing a weighing therefore
    propagated correctly in the database while the dependent row on
    screen kept its pre-save value until a full page reload -- the
    stored number and the displayed one disagreeing, which is worse
    than either of them simply being wrong.

    We already know exactly which siblings we changed, so we record
    them here and hand the list over (see _patch_listing_set_field)
    instead of widening getDependents(): that one also drives the
    retract / retest / reject guards and the after-transition cascade,
    and a display problem is no reason to move those goalposts.
    """
    local = _get_propagation_local()
    touched = getattr(local, "touched", None)
    if touched is None:
        touched = []
        local.touched = touched
    if len(touched) >= _MAX_PROPAGATION_RECORD:
        # Only a consumer knows where one logical save ends, so the
        # list is cleared by _drain_propagated_siblings rather than
        # here.  A caller that never drains -- the batch importer, for
        # one -- would otherwise keep every analysis it ever touched
        # alive for the life of the thread.  Stopping at a cap keeps
        # that bounded; the objects are already loaded in the
        # transaction, so nothing is lost but the record itself.
        return
    try:
        uid = sibling.UID()
    except Exception:
        return
    for recorded in touched:
        try:
            if recorded.UID() == uid:
                return
        except Exception:
            continue
    touched.append(sibling)


def _drain_propagated_siblings():
    """Return the siblings the current write propagated to, and forget
    them.

    Draining rather than peeking keeps a caller that never asks -- the
    batch import path, say -- from carrying objects over into the next
    write.
    """
    local = _get_propagation_local()
    touched = getattr(local, "touched", None) or []
    local.touched = []
    return list(touched)


def _patch_listing_set_field():
    """Report LOOKUP-dependent analyses from the listing save endpoint.

    AjaxListingView.set_field returns the objects a field write
    changed; ajax_set_fields then re-renders exactly those rows.  Our
    propagation changes siblings that set_field has no way of knowing
    about, so they were silently left out of both the response and the
    reindex.

    Only the siblings are affected here.  Everything the data manager
    itself reported is passed through untouched, so a listing with no
    LOOKUP in play behaves exactly as before.
    """
    try:
        from senaite.app.listing.ajax import AjaxListingView
    except Exception as _lsf_err:
        _s = __import__("sys")
        _s.stderr.write(
            "maitux: senaite.app.listing not importable yet (%s), "
            "deferring set_field patch\n" % _lsf_err)
        return False

    if "set_field" not in AjaxListingView.__dict__:
        _s = __import__("sys")
        _s.stderr.write(
            "maitux: set_field not found on AjaxListingView, skip\n")
        return False

    if getattr(AjaxListingView.set_field, "_maitux_patched", False):
        return True

    original = AjaxListingView.__dict__["set_field"]

    def patched_set_field(self, obj, name, value):
        # Bracket the write: discard anything an earlier caller left
        # behind, so what we drain afterwards belongs to this save and
        # survives however many times propagation runs inside it.
        _drain_propagated_siblings()
        updated = original(self, obj, name, value) or []
        extra = _drain_propagated_siblings()
        if not extra:
            return updated
        reported = set()
        for reported_obj in updated:
            try:
                reported.add(reported_obj.UID())
            except Exception:
                continue
        added = []
        for sibling in extra:
            try:
                if sibling.UID() in reported:
                    continue
                # The original reindexes what the data manager
                # reported; these were changed behind its back, so
                # nothing has reindexed them yet.
                sibling.reindexObject()
                added.append(sibling)
            except Exception:
                continue
        if added:
            _s = __import__("sys")
            _s.stderr.write(
                "maitux: set_field: also reporting %d "
                "LOOKUP-dependent sibling(s)\n" % len(added))
        return list(updated) + added

    patched_set_field._maitux_patched = True
    setattr(AjaxListingView, "set_field", patched_set_field)
    _s = __import__("sys")
    _s.stderr.write("maitux: set_field patch applied OK\n")
    _s.stderr.flush()
    return True


def _patch_listing_set_field_deferred(event=None):
    """Retry the set_field patch once the ZODB is up.

    apply_patches() runs while this package is being imported, which on
    a cold start can be before senaite.app.listing.ajax -- it imports
    senaite.core at module scope -- is importable.  Failing there would
    leave the patch silently absent, so the attempt is repeated from an
    IDatabaseOpenedWithRoot subscriber, by which point every product is
    loaded.  Whichever attempt wins, the other becomes a no-op.
    """
    try:
        _patch_listing_set_field()
    except Exception:
        _s = __import__("sys")
        _s.stderr.write("maitux: deferred set_field patch failed\n")


def _patch_setupdata_import():
    """ISSUE-001: XLSX setup-data importer fixes.

    Core bugs (senaite/core/exportimport/setupdata/__init__.py):

      1. Every importer created a NEW object per spreadsheet row
         (_createObjectByType(..., tmpID()) / api.create(...)) and never
         looked for an existing one, so re-importing a sheet into a
         database that already held that data silently produced same-named
         duplicates.  All five importers patched here now upsert.

         Duplicates are not merely untidy: core's get_object() returns
         None when a title matches more than one object, and its callers
         answer None with `continue`.  So a single duplicated Department
         makes every Analysis Category that references it vanish from the
         import without raising anything -- which is how this site ended
         up with two Departments of the same title and no way to notice.

      2. Method <-> Calculation relations were written to the DEPRECATED
         single-valued 'Calculation' field, while the active model (and
         AnalysisService.get_methods_calculations()) reads the
         multi-valued 'Calculations' field (1:N).

         Renaming the field is not enough.  Import order is the physical
         sheet order in the workbook, and Methods normally precedes
         Calculations, so the Calculation a Method row names does not
         exist yet when that row is processed.  Core's fallback --
         back-filling from Calculations.Import -- only matches a Method
         whose title equals the Calculation's title, a convention nobody
         follows.  The link is therefore established from BOTH sides here,
         so it lands whichever sheet comes first.

         self.defer() cannot carry this field: solve_deferred() appends
         the resolved OBJECT to the field's current value, but
         Method.setCalculations() runs filter(api.is_uid, value) and drops
         anything that is not a 32-character uid.  The deferred link would
         be a silent no-op.

      3. Analysis_Services.Import ran no keyword validation at all.
         Uniqueness is now handled by the upsert; the character-set rule
         is still enforced.  Core's check_keyword() is deliberately NOT
         used: on top of uniqueness it rejects any keyword that appears in
         a Calculation formula, and in a setup import `[as_keyword]` in a
         formula is the intended way to express a cross-analysis
         dependency, not a conflict.  Applying that rule here would make
         legitimate services disappear.

      4. The interim-field loaders mangled the boolean columns.
         `get_interim_fields()` reads

             "hidden": ("hidden" in row and row["hidden"]) and True or False

         but the sheet holds the STRING 'FALSE', and every non-empty
         string is truthy -- so one import hides every interim field in
         the workbook.  Worse, `report`, `apply_wide` and `locked` are
         never read at all, so importing over an existing Calculation
         silently drops all three on every field.  Measured on the live
         site before this fix: 1239 unintended value changes across 27
         Calculations.  Core parses only cross_referenceable correctly.

    All of this is done by monkey-patching the importer classes;
    senaite.core is left untouched.
    """
    import re
    import sys as _sys

    try:
        from senaite.core.exportimport.setupdata import Analysis_Categories
        from senaite.core.exportimport.setupdata import Analysis_Services
        from senaite.core.exportimport.setupdata import Calculations
        from senaite.core.exportimport.setupdata import Float
        from senaite.core.exportimport.setupdata import Lab_Departments
        from senaite.core.exportimport.setupdata import Methods
        from senaite.core.exportimport.setupdata import read_file
    except Exception as _sde_err:
        _sys.stderr.write(
            "maitux: setupdata module not importable yet (%s), "
            "deferring importer patches\n" % _sde_err)
        return False

    if getattr(Analysis_Services.Import, "_maitux_issue001", False):
        return True

    from Products.Archetypes.event import ObjectInitializedEvent
    from Products.CMFCore.utils import getToolByName
    from Products.CMFPlone.utils import _createObjectByType
    from bika.lims import api
    from bika.lims import logger
    from bika.lims.utils import tmpID
    from pkg_resources import resource_filename
    from senaite.core.api.analysisservice import RX_SERVICE_KEYWORD
    from senaite.core.catalog import CONTACT_CATALOG
    from senaite.core.catalog import SETUP_CATALOG
    from senaite.core.idserver import renameAfterCreation
    from zope.event import notify

    _sys.stderr.write("maitux: patching setupdata importers (ISSUE-001)\n")
    _sys.stderr.flush()

    # ------------------------------------------------------------------
    # shared helpers
    # ------------------------------------------------------------------
    def _u(value):
        """Everything to unicode.

        get_rows() hands back utf-8 `str`, object titles come back as
        either, and Py2 compares the two by codepoint -- which is how a
        title match silently fails on every non-ASCII name.
        """
        if isinstance(value, str):
            return value.decode("utf-8", "replace")
        if value is None:
            return u""
        if not isinstance(value, unicode):
            return unicode(value)
        return value

    def _label(value):
        """Unicode back to utf-8, for log messages."""
        return _u(value).encode("utf-8")

    def _to_bool(value, default=False):
        """Read a spreadsheet truth value as a boolean.

        These columns arrive as the STRINGS 'TRUE'/'FALSE', and every
        non-empty string is truthy in Python.  Core's

            "hidden": ("hidden" in row and row["hidden"]) and True or False

        therefore reads hidden='FALSE' as True and hides every interim
        field in the workbook -- one import is enough to make an entire
        result form disappear.  Core gets this right for
        cross_referenceable and nowhere else.
        """
        if value is None or value == "":
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        return _u(value).strip().lower() in (u"true", u"1", u"yes", u"x",
                                             u"y")

    def _read_interim(row, owner_column):
        """One interim-field dict from one spreadsheet row.

        Beyond the boolean parsing above, core's loaders simply never read
        `report`, `apply_wide` or `locked` -- the keys are absent from the
        dict they build, so importing over an existing Calculation drops
        those three settings on every field.  They are carried through
        here whenever the sheet has the column.
        """
        interim = {
            "keyword": row["keyword"],
            "title": row.get("title", ""),
            # core hard-codes this; left alone deliberately
            "type": "int",
            "value": row.get("value", ""),
            "unit": row.get("unit", "") or "",
            "hidden": _to_bool(row.get("hidden")),
        }
        if row.get("result_type"):
            interim["result_type"] = row["result_type"]
        if row.get("formula"):
            interim["formula"] = row["formula"]
        for col in ("report", "apply_wide", "locked", "cross_referenceable"):
            if col in row:
                interim[col] = _to_bool(row[col])
        return interim

    def _match(container, portal_type, title=None, keyword=None):
        """Objects of `portal_type` in `container` matching title/keyword.

        Walks the folder instead of querying the catalog on purpose:
        objects created earlier in the same import are not reliably
        indexed yet, and the `title` index raises UnicodeDecodeError on
        non-ASCII values in this Py2 stack.  A stale index here would mean
        a duplicate object instead of an update.  These containers hold
        tens of objects, so the walk costs nothing.
        """
        want = _u(title if keyword is None else keyword).strip()
        if not want:
            return []
        found = []
        for obj in container.objectValues():
            try:
                if api.get_portal_type(obj) != portal_type:
                    continue
                got = obj.getKeyword() if keyword is not None else obj.Title()
                if _u(got).strip() == want:
                    found.append(obj)
            except Exception:
                continue
        return found

    def _upsert(container, portal_type, sheet, title=None, keyword=None):
        """Return (obj_or_None, is_new) for this row.

        More than one match is reported and the first is used -- the only
        alternative is creating yet another duplicate, which is how the
        situation arose in the first place.
        """
        found = _match(container, portal_type, title=title, keyword=keyword)
        if not found:
            return None, True
        if len(found) > 1:
            logger.warn(
                "maitux.calcenhance: %s '%s' matches %d existing objects "
                "(%s); updating the first. Duplicates make core's "
                "get_object() return None, which silently drops every row "
                "referencing this one -- please clean them up."
                % (sheet, _label(title if keyword is None else keyword),
                   len(found), ", ".join(o.getId() for o in found)))
        return found[0], False

    def _present(row, spec):
        """Build edit kwargs from the columns the sheet actually has.

        get_rows() builds its dict with zip(headers, values), so a column
        the sheet does not contain is simply absent -- and row.get(name,
        default) then yields the default.  Core feeds those defaults
        straight into edit(), which is harmless while creating and
        destructive while updating: re-importing a Methods sheet with no
        MethodID column would blank every MethodID.

        `spec` is a list of (kwarg, column, converter); a converter of
        None passes the raw value through.
        """
        out = {}
        for kwarg, column, conv in spec:
            if column not in row:
                continue
            value = row[column]
            out[kwarg] = conv(value) if conv else value
        return out

    def _link_method_calculation(method, calculation):
        """Add `calculation` to method.Calculations, idempotently.

        Uids from end to end, because Method.setCalculations() filters its
        argument through api.is_uid.  Returns True if newly linked.
        """
        if not method or not calculation:
            return False
        try:
            uid = api.get_uid(calculation)
            current = [u for u in (method.getRawCalculations() or [])
                       if api.is_uid(u)]
            if uid in current:
                return False
            method.setCalculations(current + [uid])
            return True
        except Exception as err:
            logger.warn(
                "maitux.calcenhance: could not link a calculation to method "
                "'%s': %s" % (_label(api.get_title(method)), err))
            return False

    def _methods_sheet_pairs(importer):
        """[(method_title, calculation_title)] read straight off the sheet.

        Read from the workbook rather than through the driver, so it does
        not matter whether the Methods sheet has been processed yet.  This
        is what lets the Method <-> Calculation link be made from the
        Calculations side as well.
        """
        pairs = []
        try:
            worksheet = importer.workbook["Methods"]
        except Exception:
            return pairs
        if worksheet is None:
            return pairs
        try:
            for row in importer.get_rows(3, worksheet=worksheet):
                title = row.get("title")
                calc_title = row.get("Calculation_title")
                if title and calc_title:
                    pairs.append((title, calc_title))
        except Exception as err:
            logger.warn("maitux.calcenhance: could not read the Methods "
                        "sheet: %s" % err)
        return pairs

    # ------------------------------------------------------------------
    # Lab_Departments — upsert
    # ------------------------------------------------------------------
    def patched_departments_import(self):
        container = api.get_senaite_setup().departments
        cat = getToolByName(self.context, CONTACT_CATALOG)
        lab_contacts = [o.getObject() for o in cat(portal_type="LabContact")]
        for row in self.get_rows(3):
            title = row.get("title")
            if not title:
                continue

            obj, is_new = _upsert(container, "Department", "Department",
                                  title=title)
            values = _present(row, [("title", "title", None),
                                    ("description", "description", None)])
            if is_new:
                obj = api.create(container, "Department", **values)
            else:
                api.edit(obj, check_permissions=False, **values)

            username = row.get("LabContact_Username")
            manager = None
            for contact in lab_contacts:
                if contact.getUsername() == username:
                    manager = contact
                    break
            if manager:
                obj.setManager(manager.UID())
            elif username:
                logger.info("Department: lookup of '%s' in LabContacts"
                            "/Username failed." % username)

    # Mark the plain function BEFORE binding it to the class.  In Py2
    # `SomeClass.Import` yields an instancemethod, and setting an
    # attribute on one raises AttributeError -- reads pass through to
    # im_func, writes do not.  Doing it the other way round aborts the
    # whole patch run on the first marker, leaving every later importer
    # unpatched and the idempotency guard permanently False.
    patched_departments_import._maitux_issue001 = True
    Lab_Departments.Import = patched_departments_import

    # ------------------------------------------------------------------
    # Analysis_Categories — upsert
    # ------------------------------------------------------------------
    def patched_categories_import(self):
        container = self.context.setup.analysiscategories
        setup_tool = getToolByName(self.context, SETUP_CATALOG)
        for row in self.get_rows(3):
            title = row.get("title")
            if not title:
                logger.warning("Error in in {}. Missing Title field."
                               .format(self.sheetname))
                continue

            department_title = row.get("Department_title", None)
            if not department_title:
                logger.warning("Error in {}. Department field missing."
                               .format(self.sheetname))
                continue

            department = self.get_object(setup_tool, "Department",
                                         title=department_title)
            if not department:
                # get_object() also answers None when the title matches
                # more than one Department, so say which case this is
                # instead of blaming the spreadsheet.
                dupes = _match(api.get_senaite_setup().departments,
                               "Department", title=department_title)
                if len(dupes) > 1:
                    logger.warning(
                        "maitux.calcenhance: Analysis Category '%s' skipped: "
                        "Department '%s' exists %d times (%s). Core resolves "
                        "an ambiguous title to None. Remove the duplicates "
                        "and import again."
                        % (_label(title), _label(department_title),
                           len(dupes), ", ".join(o.getId() for o in dupes)))
                else:
                    logger.warning("Error in {}. Department '{}' is wrong."
                                   .format(self.sheetname, department_title))
                continue

            obj, is_new = _upsert(container, "AnalysisCategory",
                                  "Analysis Category", title=title)
            values = _present(row, [("title", "title", None),
                                    ("description", "description", None),
                                    ("comments", "comments", None)])
            values["department"] = department
            if is_new:
                api.create(container, "AnalysisCategory", **values)
            else:
                api.edit(obj, check_permissions=False, **values)

    patched_categories_import._maitux_issue001 = True
    Analysis_Categories.Import = patched_categories_import

    # ------------------------------------------------------------------
    # Methods — upsert, and link to the ACTIVE multi-valued field
    # ------------------------------------------------------------------
    def patched_methods_import(self):
        folder = self.context.methods
        bsc = getToolByName(self.context, SETUP_CATALOG)
        for row in self.get_rows(3):
            if not row.get("title"):
                continue

            calculation = self.get_object(
                bsc, "Calculation", row.get("Calculation_title"))
            obj, is_new = _upsert(folder, "Method", "Method",
                                  title=row["title"])
            if is_new:
                obj = _createObjectByType("Method", folder, tmpID())

            obj.edit(**_present(row, [
                ("title", "title", None),
                ("description", "description", None),
                ("Instructions", "Instructions", None),
                ("ManualEntryOfResults", "ManualEntryOfResults", None),
                ("MethodID", "MethodID", None),
                ("Accredited", "Accredited", None),
            ]))

            # Only touch Calculations when this row actually resolved one.
            # Blanking it otherwise would wipe a link a later sheet -- or a
            # person -- had already established, which is the very relation
            # the import exists to build.
            if calculation:
                _link_method_calculation(obj, calculation)
            elif row.get("Calculation_title"):
                logger.info(
                    "maitux.calcenhance: calculation '%s' for method '%s' "
                    "does not exist yet; the link will be made from the "
                    "Calculations sheet."
                    % (_label(row.get("Calculation_title")),
                       _label(row["title"])))

            if row.get("MethodDocument"):
                path = resource_filename(
                    self.dataset_project,
                    "setupdata/%s/%s" % (self.dataset_name,
                                         row["MethodDocument"])
                )
                try:
                    file_data = read_file(path)
                    obj.setMethodDocument(file_data)
                except Exception as msg:
                    logger.warning(
                        "%s Error on sheet: %s" % (msg, self.sheetname))

            if is_new:
                obj.unmarkCreationFlag()
                renameAfterCreation(obj)
                notify(ObjectInitializedEvent(obj))

    patched_methods_import._maitux_issue001 = True
    Methods.Import = patched_methods_import

    # ------------------------------------------------------------------
    # Calculations.get_interim_fields — parse the boolean columns, and
    # carry report / apply_wide / locked through
    # ------------------------------------------------------------------
    def patched_get_interim_fields(self):
        sheetname = "Calculation Interim Fields"
        worksheet = self.workbook[sheetname]
        if not worksheet:
            return
        self.interim_fields = {}
        for row in self.get_rows(3, worksheet=worksheet):
            calc_title = row["Calculation_title"]
            self.interim_fields.setdefault(calc_title, []).append(
                _read_interim(row, "Calculation_title"))

    patched_get_interim_fields._maitux_issue001 = True
    Calculations.get_interim_fields = patched_get_interim_fields

    # ------------------------------------------------------------------
    # Analysis_Services.load_interim_fields — same treatment.  This sheet
    # has no `hidden` column in core's version, so it never hit the
    # inverted boolean, but it drops the other three just the same.
    # ------------------------------------------------------------------
    def patched_load_interim_fields(self):
        sheetname = "AnalysisService InterimFields"
        worksheet = self.workbook[sheetname]
        if not worksheet:
            return
        self.service_interims = {}
        for row in self.get_rows(3, worksheet=worksheet):
            service_title = row["Service_title"]
            self.service_interims.setdefault(service_title, []).append(
                _read_interim(row, "Service_title"))

    patched_load_interim_fields._maitux_issue001 = True
    Analysis_Services.load_interim_fields = patched_load_interim_fields

    # ------------------------------------------------------------------
    # Calculations — upsert, and link back to Methods from this side
    # ------------------------------------------------------------------
    def patched_calculations_import(self):
        self.get_interim_fields()
        container = self.context.setup.calculations
        bsc = getToolByName(self.context, SETUP_CATALOG)
        method_pairs = _methods_sheet_pairs(self)

        for row in self.get_rows(3):
            calc_title = row.get("title")
            if not calc_title:
                continue

            calc_interims = self.interim_fields.get(calc_title, [])
            formula = row.get("Formula") or ""
            keywords = re.compile(r"\[([^\.^\]]+)\]").findall(formula)
            interim_keys = [k["keyword"] for k in calc_interims]
            dep_keywords = [k for k in keywords if k not in interim_keys]

            obj, is_new = _upsert(container, "Calculation", "Calculation",
                                  title=calc_title)
            if is_new:
                # api.create() routes unknown kwargs through setattr, so
                # the legacy capitalised aliases still land.
                obj = api.create(container, "Calculation",
                                 title=calc_title,
                                 description=row.get("description"),
                                 InterimFields=calc_interims,
                                 Formula=formula)
            else:
                # api.edit() filters kwargs through get_fields(), and the
                # Dexterity schema names are lower case (`formula`,
                # `interim_fields`).  'Formula' and 'InterimFields' are
                # property aliases, not fields, so passing them here would
                # be silently dropped -- go through the setters instead.
                api.edit(obj, check_permissions=False,
                         **_present(row, [
                             ("title", "title", None),
                             ("description", "description", None),
                         ]))
                obj.setInterimFields(calc_interims)
                obj.setFormula(formula)

            for kw in dep_keywords:
                self.defer(src_obj=obj,
                           src_field="dependent_services",
                           dest_catalog=SETUP_CATALOG,
                           dest_query={"portal_type": "AnalysisService",
                                       "getKeyword": kw})

            # Link every Method whose sheet row names this Calculation.
            # Matches on the Calculation_title column rather than on
            # Method title == Calculation title, which is what core
            # assumed and nobody writes.
            want = _u(calc_title).strip()
            for method_title, wanted_calc in method_pairs:
                if _u(wanted_calc).strip() != want:
                    continue
                method = self.get_object(bsc, "Method", method_title)
                if not method:
                    continue
                if _link_method_calculation(method, obj):
                    logger.info(
                        "maitux.calcenhance: linked calculation '%s' to "
                        "method '%s'"
                        % (_label(calc_title), _label(method_title)))

    patched_calculations_import._maitux_issue001 = True
    Calculations.Import = patched_calculations_import

    # ------------------------------------------------------------------
    # Analysis_Services — upsert by keyword
    # ------------------------------------------------------------------
    def patched_as_import(self):
        self.load_interim_fields()
        folder = self.context.bika_setup.bika_analysisservices
        bsc = getToolByName(self.context, SETUP_CATALOG)
        for row in self.get_rows(3):
            if not row['title']:
                continue

            keyword = row['Keyword']
            # Character set only -- see the note on check_keyword() in this
            # function's docstring for why the rest of it is not applied.
            if re.findall(RX_SERVICE_KEYWORD, keyword or ""):
                raise ValueError(
                    "maitux.calcenhance: Analysis Service '%s' has an "
                    "invalid keyword %r -- only letters, digits, '-' and "
                    "'_' are allowed. Refusing to import a service that no "
                    "formula could ever reference."
                    % (_label(row['title']), keyword))

            obj, is_new = _upsert(folder, "AnalysisService",
                                  "Analysis Service", keyword=keyword)
            if is_new:
                obj = _createObjectByType("AnalysisService", folder, tmpID())

            MTA = {
                'days': self.to_int(row.get('MaxTimeAllowed_days', 0), 0),
                'hours': self.to_int(row.get('MaxTimeAllowed_hours', 0), 0),
                'minutes': self.to_int(row.get('MaxTimeAllowed_minutes', 0), 0),
            }
            category = self.get_object(
                bsc, 'AnalysisCategory', row.get('AnalysisCategory_title'))
            department = self.get_object(
                bsc, 'Department', row.get('Department_title'))
            container = self.get_object(
                bsc, 'SampleContainer', row.get('Container_title'))
            preservation = self.get_object(
                bsc, 'SamplePreservation', row.get('Preservation_title'))

            # Analysis Service - Method considerations:
            # One Analysis Service can have 0 or n Methods associated (field
            # 'Methods' from the Schema).
            # If the Analysis Service has at least one method associated, then
            # one of those methods can be set as the defualt method (field
            # '_Method' from the Schema).
            #
            # To make it easier, if a DefaultMethod is declared in the
            # Analysis_Services spreadsheet, but the same AS has no method
            # associated in the Analysis_Service_Methods spreadsheet, then make
            # the assumption that the DefaultMethod set in the former has to be
            # associated to the AS although the relation is missing.
            defaultmethod = self.get_object(
                bsc, 'Method', row.get('DefaultMethod_title'))
            methods = self.get_methods(row['title'], defaultmethod)
            if not defaultmethod and methods:
                defaultmethod = methods[0]

            # Analysis Service - Instrument considerations:
            # By default, an Analysis Services will be associated automatically
            # with several Instruments due to the Analysis Service - Methods
            # relation (an Instrument can be assigned to a Method and one Method
            # can have zero or n Instruments associated). There is no need to
            # set this assignment directly, the AnalysisService object will
            # find those instruments.
            # Besides this 'automatic' behavior, an Analysis Service can also
            # have 0 or n Instruments manually associated ('Instruments' field).
            # In this case, the attribute 'AllowInstrumentEntryOfResults' should
            # be set to True.
            #
            # To make it easier, if a DefaultInstrument is declared in the
            # Analysis_Services spreadsheet, but the same AS has no instrument
            # associated in the AnalysisService_Instruments spreadsheet, then
            # make the assumption the DefaultInstrument set in the former has
            # to be associated to the AS although the relation is missing and
            # the option AllowInstrumentEntryOfResults will be set to True.
            defaultinstrument = self.get_object(
                bsc, 'Instrument', row.get('DefaultInstrument_title'))
            instruments = self.get_instruments(row['title'], defaultinstrument)
            allowinstrentry = True if instruments else False
            if not defaultinstrument and instruments:
                defaultinstrument = instruments[0]

            # The manual entry of results can only be set to false if the value
            # for the attribute "InstrumentEntryOfResults" is False.
            allowmanualentry = True if not allowinstrentry else row.get(
                'ManualEntryOfResults', True)

            # Analysis Service - Calculation considerations:
            # By default, the AnalysisService will use the Calculation associated
            # to the Default Method (the field "UseDefaultCalculation"==True).
            # If the Default Method for this AS doesn't have any Calculation
            # associated and the field "UseDefaultCalculation" is True, no
            # Calculation will be used for this AS ("_Calculation" field is
            # reserved and should not be set directly).
            #
            # To make it easier, if a Calculation is set by default in the
            # spreadsheet, then assume the UseDefaultCalculation has to be set
            # to False.
            deferredcalculation = self.get_object(
                bsc, 'Calculation', row.get('Calculation_title'))
            usedefaultcalculation = False if deferredcalculation else True
            # Read the ACTIVE multi-valued field of the default method; the
            # deprecated singular getCalculation() is never populated.
            _calculation = deferredcalculation if deferredcalculation else None
            if not _calculation and defaultmethod:
                method_calcs = defaultmethod.getCalculations()
                if method_calcs:
                    _calculation = method_calcs[0]

            obj.edit(
                title=row['title'],
                ShortTitle=row.get('ShortTitle', row['title']),
                description=row.get('description', ''),
                Keyword=row['Keyword'],
                PointOfCapture=row['PointOfCapture'].lower(),
                Category=category,
                Department=department,
                Unit=row['Unit'] and row['Unit'] or None,
                Precision=row['Precision'] and str(row['Precision']) or '0',
                ExponentialFormatPrecision=str(self.to_int(
                    row.get('ExponentialFormatPrecision', 7), 7)),
                LowerDetectionLimit='%06f' % self.to_float(
                    row.get('LowerDetectionLimit', '0.0'), 0),
                UpperDetectionLimit='%06f' % self.to_float(
                    row.get('UpperDetectionLimit', '1000000000.0'), 1000000000.0),
                DetectionLimitSelector=self.to_bool(
                    row.get('DetectionLimitSelector', 0)),
                MaxTimeAllowed=MTA,
                Price="%02f" % Float(row['Price']),
                BulkPrice="%02f" % Float(row['BulkPrice']),
                VAT="%02f" % Float(row['VAT']),
                _Method=defaultmethod,
                Methods=methods,
                ManualEntryOfResults=allowmanualentry,
                InstrumentEntryOfResults=allowinstrentry,
                Instruments=instruments,
                Calculation=_calculation,
                UseDefaultCalculation=usedefaultcalculation,
                DuplicateVariation="%02f" % Float(row['DuplicateVariation']),
                Accredited=self.to_bool(row['Accredited']),
                InterimFields=hasattr(self, 'service_interims') and self.service_interims.get(
                    row['title'], []) or [],
                Separate=self.to_bool(row.get('Separate', False)),
                Container=container,
                Preservation=preservation,
                CommercialID=row.get('CommercialID', ''),
                ProtocolID=row.get('ProtocolID', '')
            )
            if is_new:
                obj.unmarkCreationFlag()
                renameAfterCreation(obj)
                notify(ObjectInitializedEvent(obj))
        self.load_result_options()
        self.load_service_uncertainties()

    patched_as_import._maitux_issue001 = True
    Analysis_Services.Import = patched_as_import

    return True


def _patch_setupdata_import_deferred(event=None):
    """Retry the setupdata importer patches once the ZODB is up."""
    try:
        _patch_setupdata_import()
    except Exception:
        _s = __import__("sys")
        _s.stderr.write("maitux: deferred setupdata import patch failed\n")


def _propagate_lookup_recalc(analysis):
    """Re-evaluate siblings that LOOKUP-reference `analysis` (transitively).

    A thread-local visited set (keyed by analysis UID) breaks cycles such as
    mutually-referencing analyses (A LOOKUP B and B LOOKUP A).
    """
    local = _get_propagation_local()
    visited = getattr(local, "visited", None)
    if visited is None:
        visited = set()
        local.visited = visited
        visited.add(analysis.UID())
    elif analysis.UID() in visited:
        return
    else:
        visited.add(analysis.UID())

    for sibling in _dependent_sibling_analyses(analysis):
        before_values = _interim_value_map(sibling)
        _evaluate_interims_ordered(sibling)
        # Writing a sibling here used to leave no audit trail at all:
        # the snapshot is taken by the auditlog subscriber, which only
        # runs on an event, and nothing on this path fired one.  The
        # Audit Log tab therefore kept reporting the pre-propagation
        # value -- actively contradicting the stored one -- with no
        # record of who or what changed it.
        #
        # An Analysis is an Archetypes object, and for those the
        # subscriber is registered on Products.Archetypes
        # IObjectEditedEvent, NOT zope.lifecycleevent
        # IObjectModifiedEvent (that one is bound to Dexterity
        # content only), so IObjectEditedEvent is the event to fire.
        if not _same_value_map(before_values,
                               _interim_value_map(sibling)):
            _record_propagated_sibling(sibling)
            try:
                _notify_event(_ATObjectEditedEvent(sibling))
            except Exception:
                from bika.lims import logger as _prop_logger
                _prop_logger.exception(
                    "maitux.calcenhance: could not notify edit of %s"
                    % getattr(sibling, "id", "?"))
        _propagate_lookup_recalc(sibling)


def _finish_propagation():
    _get_propagation_local().visited = None


# ==============================================================================
# CALCULATED INTERIM EVALUATION ENGINE
# ==============================================================================

# Prefix for the variables a formula's [keyword] references get bound to.  It
# keeps them clear of the function whitelist -- an interim may legitimately be
# called "sum", "min" or "avg".
_VAR_PREFIX = "_maitux_v_"


def _bind_formula_values(expr, token_re, resolve):
    """Turn [keyword] references into variable names and collect their values.

    Returns (expr, variables), ready for eval(expr, globals, variables).
    `resolve(keyword)` yields the value, or None to leave the reference alone.

    Values are *bound*, never rendered into the expression text.  The previous
    approach wrapped strings in double quotes and interpolated them with
    `expr % mapping`, which made every analyst-entered value part of the
    evaluated source:

      - a value containing a double quote (a pasted sample or solvent name)
        produced a SyntaxError, and since evaluation failures are swallowed the
        field simply stopped updating, with no hint as to why;
      - a crafted value could smuggle in an expression of its own.  The
        function whitelist does not help there: it replaces __builtins__ but
        does not block attribute access, so `().__class__` remains reachable.

    Binding removes both problems at once: quotes are just characters again,
    and a value can never be parsed as code.
    """
    import bika.lims.api as api

    variables = {}
    for match in token_re.finditer(expr):
        keyword = match.group(1)
        value = resolve(keyword)
        if value is None:
            continue
        name = _VAR_PREFIX + keyword
        expr = expr.replace("[%s]" % keyword, name)
        if isinstance(value, bool):
            variables[name] = value
        elif isinstance(value, (int, float)):
            variables[name] = float(value)
        elif api.is_floatable(value):
            variables[name] = float(value)
        else:
            variables[name] = _safe_text(value)
    return expr, variables


# ISSUE-020 step 1 -- reporting only, evaluation order is untouched.
# The engines define their own _TOKEN_RE inside their bodies, so this
# needs its own copy.  `re` is not bound at module level here (only
# `import re as _lookup_re` further up), so import it explicitly
# rather than relying on that alias staying where it is.
import re as _order_re

_ORDER_TOKEN_RE = _order_re.compile(r'\[([A-Za-z_]\w*)\]')


def _interim_order_violations(interims):
    """Formulas that reference a keyword defined after themselves.

    Returns [(keyword, index, referenced_keyword, referenced_index)].

    Evaluation is meant to follow the order the fields are defined in the
    Calculation -- an order QA can read straight off the configuration.  A
    forward reference breaks that promise.  It still produces a value
    today, but only because writing a result re-enters evaluation and a
    later pass happens to pick the dependency up; a long chain can exceed
    _MAX_EVAL_DEPTH and then the field silently stays "---".

    Keywords that match no local field are ignored: those are
    cross-analysis LOOKUP arguments, whose ordering belongs to the
    propagation mechanism, not to this one.
    """
    first_index = {}
    for index, interim in enumerate(interims):
        keyword = interim.get("keyword")
        if keyword and keyword not in first_index:
            first_index[keyword] = index

    violations = []
    for index, interim in enumerate(interims):
        keyword = interim.get("keyword")
        formula = interim.get("formula") or ""
        if not keyword or not formula:
            continue
        for referenced in sorted(set(_ORDER_TOKEN_RE.findall(formula))):
            if referenced == keyword:
                continue
            referenced_index = first_index.get(referenced)
            if referenced_index is None:
                continue
            if referenced_index > index:
                violations.append(
                    (keyword, index, referenced, referenced_index))
    return violations


def _report_interim_order(analysis, interims):
    """Log any forward reference.  Reports only, changes nothing."""
    try:
        violations = _interim_order_violations(interims)
    except Exception:
        return
    if not violations:
        return
    from bika.lims import logger as _order_logger
    listed = ", ".join("%s(#%d) -> %s(#%d)" % v for v in violations)
    _order_logger.warn(
        "maitux.calcenhance: %s has %d interim(s) that reference a keyword "
        "defined after themselves; evaluation follows the Calculation "
        "field order, so move the dependency earlier: %s"
        % (getattr(analysis, "id", "?"), len(violations), listed))


def _interim_runs(interims):
    """Contiguous runs of formula-bearing fields, in definition order.

    Returns [(engine, [keyword, ...]), ...] with engine in
    ("scalar", "list").  Evaluation follows the order the fields are
    defined -- an order QA can read straight off the configuration --
    so the work is grouped into runs of consecutive fields handled by
    the same engine and the runs run front to back.

    Runs rather than one call per field: each engine rebuilds its whole
    context (value_map / list_arrays / str_arrays / function
    whitelist) on every call, so per-field calls would be quadratic.
    """
    runs = []
    for interim in interims:
        keyword = interim.get("keyword")
        formula = (interim.get("formula") or "").strip()
        if not keyword or not formula:
            continue
        result_type = interim.get("result_type", "")
        if result_type == "calculated":
            engine = "scalar"
        elif result_type == "calculatedlist":
            engine = "list"
        else:
            continue
        if runs and runs[-1][0] == engine:
            runs[-1][1].append(keyword)
        else:
            runs.append((engine, [keyword]))
    return runs


def _evaluate_interims_ordered(self):
    """Evaluate every computed interim, in definition order.

    One sweep suffices when the field order satisfies the dependencies.
    A second sweep means this analysis stores an order that does not --
    which happens legitimately, because SENAITE snapshots the
    calculation onto the analysis when it is linked and later template
    edits deliberately do not reach it.  Such an analysis keeps working
    and the extra sweep is logged rather than hidden.
    """
    if getattr(_eval_depth_local, "in_driver", False):
        # A write from inside a run re-enters setInterimFields; this
        # sweep is already handling evaluation.
        return
    try:
        interims = self.getInterimFields() or []
    except Exception:
        return
    runs = _interim_runs(interims)
    if not runs:
        return

    _eval_depth_local.in_driver = True
    try:
        for sweep in range(_MAX_ORDER_SWEEPS):
            before = _interim_value_map(self)
            for engine, keywords in runs:
                only = set(keywords)
                if engine == "scalar":
                    _evaluate_calculated_interims(
                        self, only=only, chain=False)
                else:
                    _evaluate_calculatedlist_interims(self, only=only)
            if _same_value_map(before, _interim_value_map(self)):
                break
            if sweep:
                from bika.lims import logger as _sweep_logger
                _sweep_logger.warn(
                    "maitux.calcenhance: %s needed sweep %d to settle; "
                    "its stored interim order does not satisfy its own "
                    "dependencies (see _interim_order_violations)"
                    % (getattr(self, "id", "?"), sweep + 1))
    finally:
        _eval_depth_local.in_driver = False


def _evaluate_calculated_interims(self, only=None, chain=True):
    """Re-evaluate all Calculated-type interim fields in dependency order.

    1. Builds a dependency graph from formula [keyword] references
    2. Topologically sorts Calculated interims
    3. Evaluates in order, so DilutionFactor is ready when Content1/2 need it
    """
    import bika.lims.api as api
    import re
    import sys as _eci_sys

    # deepcopy: getInterimFields() returns the persistent list itself, so the
    # computed values below would otherwise be written into the stored data
    # before setInterimFields() gets a chance to compare against it.  A
    # Calculated field that is also flagged cross_referenceable (the response
    # factor "F" in the README example is exactly that) would then look
    # unchanged, and dependent analyses would never be re-evaluated.
    interims = deepcopy(self.getInterimFields())
    _eci_sys.stderr.write("maitux: _evaluate_calculated_interims called, %d interims\n" % len(interims))
    _eci_sys.stderr.flush()
    if not interims:
        return

    # Reports only -- evaluation order is unchanged (ISSUE-020 step 1).
    _report_interim_order(self, interims)

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
        # Even if no "calculated" interims, still try calculatedlist evaluation
        _eci_sys.stderr.write("maitux: no calculated interims found, trying calculatedlist only\n")
        _eci_sys.stderr.flush()
        if chain:
            _evaluate_calculatedlist_interims(self)
        return

    _eci_sys.stderr.write("maitux: found %d calculated interims: %s\n" % (
        len(calculated), [c["keyword"] for c in calculated]))
    _eci_sys.stderr.flush()

    # --- Step 2: build value map from current non-calculated values ---
    value_map = {}
    import json as _jj2
    list_arrays = {}  # keyword → [float, ...] for sum([KW])/max([KW])/...
    str_arrays = {}   # keyword → [str, ...] for INDEX_BY key matching
    for i in interims:
        kw = i.get("keyword", "")
        val = i.get("value", "")
        if not kw:
            continue
        rt = i.get("result_type", "")
        if rt == "calculated":
            try:
                value_map[kw] = float(val or 0)
            except (ValueError, TypeError):
                value_map[kw] = val or ""
        elif rt in ("list", "calculatedlist") and val:
            # Auto-average for bare [KW] references (backward compat)
            # Also preserve raw array for sum([KW]) / max([KW]) / ...
            try:
                arr = _jj2.loads(str(val))
                if isinstance(arr, list) and arr:
                    nums = []
                    str_vals = []
                    for v in arr:
                        try:
                            nums.append(float(str(v)))
                        except (ValueError, TypeError):
                            pass
                        # Also collect as unicode strings for INDEX_BY
                        if v is None:
                            str_vals.append(u"")
                        elif isinstance(v, unicode):
                            str_vals.append(v)
                        elif isinstance(v, str):
                            str_vals.append(v.decode("utf-8", "replace"))
                        else:
                            str_vals.append(unicode(v))
                    if nums:
                        value_map[kw] = sum(nums) / len(nums)
                        list_arrays[kw] = nums
                    else:
                        value_map[kw] = val
                    str_arrays[kw] = str_vals
                else:
                    value_map[kw] = val
            except Exception:
                value_map[kw] = val
        else:
            try:
                value_map[kw] = float(val)
            except (ValueError, TypeError):
                value_map[kw] = val

    # --- Step 3: topological sort by dependency ---
    _TOKEN_RE = re.compile(r'\[([A-Za-z_]\w*)\]')

    # --- Step 3b: cross-service lookup ---
    # If [keyword] not found in local interims, try sibling analyses in
    # the same AR (SENAITE natively supports this in calculateResult
    # via getDependencies()). This allows e.g. [S1905-KF] in a
    # Calculated sub-formula to auto-read the moisture result.
    local_keywords = set()
    for i in interims:
        kw = i.get("keyword", "")
        if kw:
            local_keywords.add(kw)
    all_refs = set()
    for c in calculated:
        for match in _TOKEN_RE.finditer(c.get("formula", "") or ""):
            all_refs.add(match.group(1))
    external_refs = all_refs - local_keywords
    if external_refs:
        try:
            # Whole sample tree, partitions included -- same scope as LOOKUP,
            # otherwise a moisture test moved to another partition becomes
            # invisible to [KEYWORD] references.
            analyses = _sample_tree_analyses(self)
            for analysis in analyses:
                if analysis.UID() == self.UID():
                    continue
                svc = analysis.getAnalysisService()
                svc_kw = svc.getKeyword() if svc else ""
                if svc_kw in external_refs:
                    result = analysis.getResult()
                    if result:
                        try:
                            value_map[svc_kw] = float(str(result))
                        except (ValueError, TypeError):
                            value_map[svc_kw] = result
        except Exception:
            pass  # cross-service lookup is best-effort

    # Build dependency graph.  Only count dependencies between Calculated
    # interims: manual/list inputs are already loaded into value_map (Step 2)
    # and must NOT block the topological sort, otherwise their in-degree is
    # never decremented (only Calculated fields decrement dependents), the
    # Kahn queue stays empty and every field silently falls back to definition
    # order.
    calculated_keywords = {c["keyword"] for c in calculated}
    deps_of = {}   # keyword → set of keywords it depends on
    for c in calculated:
        kw = c["keyword"]
        formula = c.get("formula", "") or ""
        deps_of[kw] = set()
        for match in _TOKEN_RE.finditer(formula):
            dep_kw = match.group(1)
            if dep_kw != kw and dep_kw in calculated_keywords:
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

    # Append any remaining (circular dependency — process anyway)
    seen = {c["keyword"] for c in order}
    for c in calculated:
        if c["keyword"] not in seen:
            order.append(c)

    # --- Step 4: evaluate in topological order ---
    changed = False

    # Regex for aggregate functions wrapping List keywords
    # sum([PeakArea]) → sum([1.0, 2.0, 3.0])
    # stdev([PeakArea]) → stdev([1.0, 2.0, 3.0]) — needs raw array
    # SLOPE([y], [x]) → SLOPE([1.0, 2.0], [3.0, 4.0])
    _AGG_RE = re.compile(
        r'\b(sum|max|min|avg|len|stdev|SLOPE|INTERCEPT|RSQ)\s*\(\s*'
        r'\[([A-Za-z_]\w*)\]\s*'
        r'(?:,\s*\[([A-Za-z_]\w*)\]\s*)?\)'
    )

    def _replace_agg(match):
        func_name = match.group(1)
        kw1 = match.group(2)
        kw2 = match.group(3)
        if func_name in ("SLOPE", "INTERCEPT", "RSQ"):
            if kw1 in list_arrays and kw2 in list_arrays:
                return "%s(%s, %s)" % (
                    func_name, repr(list_arrays[kw1]), repr(list_arrays[kw2]))
        else:
            if kw1 in list_arrays:
                return "%s(%s)" % (func_name, repr(list_arrays[kw1]))
        return match.group(0)

    # INDEX_BY([target], [key], match_val) — replace first two with raw arrays
    _INDEX_BY_RE = re.compile(
        r'INDEX_BY\s*\(\s*\[([A-Za-z_]\w*)\]\s*,\s*\[([A-Za-z_]\w*)\]\s*,\s*([^)]+)\)')
    _INDEX_BY_KW_RE = re.compile(r'\[([A-Za-z_]\w*)\]')

    def _replace_index_by(match):
        target_kw = match.group(1)
        key_kw = match.group(2)
        rest = match.group(3).strip()
        target_arr = list_arrays.get(target_kw, [])
        key_arr = str_arrays.get(key_kw, [])
        # If third arg is a [kw] ref, resolve it now (avoid bare-string eval issue)
        kw3_match = _INDEX_BY_KW_RE.match(rest)
        if kw3_match:
            ref_kw = kw3_match.group(1)
            if ref_kw in value_map:
                val = value_map[ref_kw]
                if isinstance(val, (str, unicode)):
                    rest = repr(val)  # quote for eval, e.g. 'B' → "'B'"
                elif isinstance(val, (int, float)):
                    rest = repr(val)
        return "INDEX_BY(%s, %s, %s)" % (repr(target_arr), repr(key_arr), rest)

    # --- Step 3c: collect cross-referenceable sibling data for LOOKUP ---
    sibling_data = _collect_cross_referenceable_data(self)
    LOOKUP = _make_lookup(sibling_data)

    def _scalar_coalesce(*values):
        """First present value.  See the list engine's _coalesce."""
        flat = []
        for value in values:
            if isinstance(value, (list, tuple)):
                flat.extend(value)
            else:
                flat.append(value)
        chosen, disagreeing = _coalesce_pick(flat)
        if disagreeing:
            from bika.lims import logger as _sc_logger
            _sc_logger.warn(
                "maitux.calcenhance: COALESCE on %s found more than one "
                "source with a value: kept %r (the first argument wins) "
                "and ignored %r -- decide which source is authoritative"
                % (getattr(self, "id", "?"), chosen, disagreeing))
        return chosen

    # Strip invisible Unicode formatting chars that creep in via copy-paste
    _INVISIBLE_RE_SCALAR = re.compile(
        u'[\u200b\u200c\u200d\u200e\u200f\ufeff\u00ad\u2060\u2061\u2062\u2063\u2064\u202a\u202b\u202c\u202d\u202e\ufffc]'
    )

    for c in order:
        formula = c.get("formula", "") or ""
        kw = c.get("keyword", "")

        if not formula or not kw:
            continue

        # Restricted to one run by the ordered driver.  The context
        # above is still built from every field, only the evaluation
        # is narrowed.
        if only is not None and kw not in only:
            continue

        # Sanitize: remove invisible formatting characters
        if isinstance(formula, str):
            formula = formula.decode("utf-8", "replace")
        formula = _INVISIBLE_RE_SCALAR.sub(u"", formula)

        # Step 4a: Replace aggregate functions wrapping List keywords
        # e.g. sum([PeakArea]) → sum([102300.0, 102350.0, 102400.0])
        expr = _AGG_RE.sub(_replace_agg, formula)
        expr = _INDEX_BY_RE.sub(_replace_index_by, expr)

        # Safe eval globals (defined before mapping check so both paths can use)
        safe_globals = {"__builtins__": {
            "abs": abs, "round": round, "len": len, "pow": pow,
            "True": True, "False": False, "None": None,
            # Aggregates skip missing members and report "---" when
            # nothing is left, instead of 0 -- an empty set has no mean,
            # and reporting 0 invents a number nobody measured.
            "max": _skip_max, "min": _skip_min, "sum": _skip_sum,
            "avg": _skip_avg,
            "floor": __import__("math").floor,
            "ceil": __import__("math").ceil,
            "sqrt": __import__("math").sqrt,
            "stdev": _skip_stdev,
            "log": __import__("math").log,
            "log10": __import__("math").log10,
            "exp": __import__("math").exp,
            "LOOKUP": LOOKUP,
            "COALESCE": _scalar_coalesce,
            "INDEX_BY": lambda target, keys, match: next(
                (target[i] for i, k in enumerate(keys) if (
                    (k if isinstance(k, unicode) else (
                        k.decode("utf-8") if isinstance(k, str) else unicode(k))
                    ) == (
                        match if isinstance(match, unicode) else (
                            match.decode("utf-8") if isinstance(match, str) else unicode(match))
                    )
                # Not found used to yield None, and the scalar engine stores
                # str(result) -- so the field literally read "None".
                )), _PLACEHOLDER),
            "SLOPE": lambda y, x: (
                (len(y) * sum(xi * yi for xi, yi in zip(x, y)) - sum(x) * sum(y)) /
                (len(y) * sum(xi * xi for xi in x) - sum(x) ** 2)
                if len(y) > 1 and (len(y) * sum(xi * xi for xi in x) - sum(x) ** 2) != 0
                else 0.0),
            "INTERCEPT": lambda y, x: (
                (sum(y) * sum(xi * xi for xi in x) - sum(x) * sum(xi * yi for xi, yi in zip(x, y))) /
                (len(y) * sum(xi * xi for xi in x) - sum(x) ** 2)
                if len(y) > 1 and (len(y) * sum(xi * xi for xi in x) - sum(x) ** 2) != 0
                else 0.0),
            "RSQ": lambda y, x: (
                lambda r: r * r)((
                    (len(y) * sum(xi*yi for xi,yi in zip(x,y)) - sum(x)*sum(y)) /
                    (((len(y)*sum(xi*xi for xi in x) - sum(x)**2) ** 0.5) *
                     ((len(y)*sum(yi*yi for yi in y) - sum(y)**2) ** 0.5))
                ) if len(y) > 1 and (
                    len(y)*sum(xi*xi for xi in x) - sum(x)**2 != 0 and
                    len(y)*sum(yi*yi for yi in y) - sum(y)**2 != 0
                ) else 0.0),
        }}

        # Step 4b: bind the remaining [keyword] references (averaged value_map)
        expr, variables = _bind_formula_values(expr, _TOKEN_RE, value_map.get)

        # Bind the "---" placeholder to the sentinel, so a missing operand
        # can never be taken for text (and silently repeated, compared or
        # minimised -- see _Missing).  Aggregates filter it out; every
        # operator refuses it, which the handlers below turn into "---".
        for _var_name in list(variables):
            if _is_missing(variables[_var_name]):
                variables[_var_name] = _MISSING

        # No [keyword] left to bind.  Either a substitution above already
        # inlined the values (avg([rf]) → avg([725.63, ...])), or the formula
        # never referenced a keyword at all -- a bare LOOKUP("as","field",...)
        # with literal arguments, or a constant like (200*1)/(10*1000).
        #
        # Do NOT gate this on `expr != formula`: "nothing was substituted" is
        # not the same as "nothing to compute", and that test silently skipped
        # every self-contained formula, leaving the field empty forever.
        if not variables:
            try:
                result = eval(expr, safe_globals, {})
                new_value = (_PLACEHOLDER if _is_missing(result)
                             else str(result))
            except Exception as _nv_err:
                _eci_sys.stderr.write(
                    "maitux: [%s] literal-only eval FAILED: %s expr=%s\n"
                    % (kw, str(_nv_err), expr[:200]))
                _eci_sys.stderr.flush()
                # A formula that cannot be evaluated has no result.
                # Leaving the field untouched kept a previously computed
                # number on display even though it no longer follows from
                # the current inputs, so write the "---" placeholder.
                new_value = _PLACEHOLDER
            old_value = c.get("value", "")
            if not _same_value(old_value, new_value):
                c["value"] = new_value
                changed = True
            try:
                value_map[kw] = float(new_value)
            except (ValueError, TypeError):
                value_map[kw] = new_value
            continue

        try:
            result = eval(expr, safe_globals, variables)
            new_value = _PLACEHOLDER if _is_missing(result) else str(result)

        except Exception as _eval_err:
            _eci_sys.stderr.write("maitux: [%s] eval FAILED: %s expr=%s vars=%s\n" % (
                kw, str(_eval_err), expr[:200], str(sorted(variables))[:200]))
            _eci_sys.stderr.flush()
            # Either an input is missing (an operator refused the
            # sentinel) or the formula genuinely cannot be evaluated.
            # Both mean "no result": write the placeholder rather than
            # leaving a stale number that no longer follows from the
            # current inputs.
            new_value = _PLACEHOLDER

        # Update the interim field AND the value_map for downstream deps
        old_value = c.get("value", "")
        if not _same_value(old_value, new_value):
            c["value"] = new_value
            changed = True
        # Keep value_map in step either way, so downstream Calculated
        # fields see the placeholder instead of a stale number.
        try:
            value_map[kw] = float(new_value)
        except (ValueError, TypeError):
            value_map[kw] = new_value

    if changed:
        self.setInterimFields(interims)

    # --- Step 5: evaluate CalculatedList interims (element-wise pairing) ---
    # Skipped when the ordered driver is in charge: it runs the array
    # runs itself, in their place in the definition order.
    if not chain:
        return
    import sys as _eci_sys
    _eci_sys.stderr.write("maitux: _evaluate_calculated_interims -> calling _evaluate_calculatedlist_interims\n")
    _eci_sys.stderr.flush()
    _evaluate_calculatedlist_interims(self)


# ==============================================================================
# UIDCATALOG UNICODE PATCH — Fix UnicodeDecodeError when title contains CJK
# ==============================================================================

def _patch_uidcatalog_unicode():
    """Patch added_handler/modified_handler in uidcatalog to handle Unicode paths.

    When creating objects with Chinese/UTF-8 titles, the physical path
    contains UTF-8 bytes that cause UnicodeDecodeError in the catalog
    indexer.  We use the UUID (always ASCII) as the catalog id instead
    of the physical path to avoid this entirely.
    """
    from plone.uuid.interfaces import IUUID

    try:
        from plone.app.referenceablebehavior import uidcatalog
    except ImportError:
        return

    _original_added = uidcatalog.added_handler

    def patched_added_handler(obj, event):
        uid_catalog, ref_catalog = uidcatalog._get_catalogs(obj)
        uid = IUUID(obj.aq_base, None)
        if uid is None:
            uid = '/'.join(obj.getPhysicalPath())
        uid_catalog.catalog_object(obj, str(uid))

    uidcatalog.added_handler = patched_added_handler

    _original_modified = uidcatalog.modified_handler

    def patched_modified_handler(obj, event):
        uid_catalog, ref_catalog = uidcatalog._get_catalogs(obj)
        uid = IUUID(obj.aq_base, None)
        if uid is None:
            uid = '/'.join(obj.getPhysicalPath())
        uid_catalog.catalog_object(obj, str(uid))

        annotations = getattr(
            getattr(obj, '_getReferenceAnnotations', lambda: None)(),
            'objectValues', lambda: [])()
        if not annotations:
            return

        for ref in annotations:
            url = uidcatalog.getRelURL(ref_catalog, ref.getPhysicalPath())
            uid_catalog.catalog_object(ref, url)
            ref_catalog.catalog_object(ref, url)
            ref._catalogRefs(uid_catalog, uid_catalog, ref_catalog)

    uidcatalog.modified_handler = patched_modified_handler



# ==============================================================================
# CALCULATEDLIST EVALUATION — Element-wise pairing
# ==============================================================================

def _evaluate_calculatedlist_interims(self, only=None):
    """Evaluate CalculatedList-type interims with element-wise pairing.

    When a CalculatedList formula references List-type interims, each
    element of the List array is paired with the corresponding element
    of other List arrays to produce individual results. Non-List deps
    (Calculated scalars, plain numbers) are broadcast to all elements.

    Example:
      StdPeakArea    = [102300, 102350, 102400]  (3 injections, List)
      SplPeakArea    = [98340, 98760, 98550]     (3 injections, List)
      DilutionFactor = 50.2                       (Calculated scalar)
      Formula: [SplPeakArea] * 200 / ([DilutionFactor] * [RF])
      -> evaluates 3 times -> [98.50, 98.84, 98.28]
    """
    import bika.lims.api as api
    import re
    import json as _jj

    # deepcopy for the same reason as in _evaluate_calculated_interims: the
    # element-wise results must not land in the persistent list before
    # setInterimFields() has snapshotted the previous state.
    interims = deepcopy(self.getInterimFields())
    if not interims:
        return

    # Collect CalculatedList items, raw List arrays, string arrays, and Calculated scalars
    cl_items = []
    list_arrays = {}     # keyword -> [float, ...]
    str_arrays = {}      # keyword -> [str, ...] for non-numeric list values (e.g. solvent names)
    # keyword -> value.  Numbers land here as floats, non-numeric values
    # as text: the array side already splits list_arrays (numeric) from
    # str_arrays (text), and the scalar side used to keep only the numeric
    # half.  A text scalar was therefore invisible to every calculatedlist
    # formula, so RESULT_NUM / INDEX_BY / LOOKUP -- which match BY NAME --
    # could not see the name they were given (ISSUE-024).
    calc_scalars = {}

    for i in interims:
        kw = i.get("keyword", "")
        rt = i.get("result_type", "")
        val = i.get("value", "")

        if rt == "calculatedlist" and i.get("formula", "").strip():
            cl_items.append(i)

        if not val or not kw:
            continue

        if rt in ("list", "calculatedlist"):
            try:
                arr = _jj.loads(str(val))
                if isinstance(arr, list) and arr:
                    def _to_unicode(v):
                        if v is None:
                            return u""
                        if isinstance(v, unicode):
                            return v
                        if isinstance(v, str):
                            return v.decode("utf-8", "replace")
                        return unicode(v)

                    # Mixed arrays (numeric + "---" placeholder) keep the
                    # placeholder rows so downstream element-wise formulas stay
                    # row-aligned.  Store them in list_arrays with numbers as
                    # floats and "---" as a string.
                    if any(v == _PLACEHOLDER for v in arr):
                        typed = []
                        for v in arr:
                            if v == _PLACEHOLDER:
                                typed.append(_PLACEHOLDER)
                            elif v is not None and v != "" and (
                                    isinstance(v, (int, float)) or api.is_floatable(v)):
                                typed.append(float(v))
                            else:
                                typed.append(_to_unicode(v))
                        list_arrays[kw] = typed
                    else:
                        # Try to interpret as numeric array first
                        nums = [float(str(v)) for v in arr
                                if v is not None and v != "" and (
                                    isinstance(v, (int, float)) or api.is_floatable(v))]
                        if nums and len(nums) == len(arr):
                            list_arrays[kw] = nums
                        else:
                            # Non-numeric list → store as string array
                            # Python 2: str(u"\u4e2d\u6587") → UnicodeEncodeError
                            str_arrays[kw] = [_to_unicode(v) for v in arr]
            except Exception:
                pass

        elif rt == "calculated":
            try:
                calc_scalars[kw] = float(val or 0)
            except (ValueError, TypeError):
                # Not a number: keep the text.  Dropping it left the
                # formula referencing an unbound name, which raised and
                # gave the whole column '---'.
                calc_scalars[kw] = _safe_text(val)
        else:
            try:
                calc_scalars[kw] = float(val)
            except (ValueError, TypeError):
                if val not in (None, ""):
                    calc_scalars[kw] = _safe_text(val)

    import sys as _dl_sys
    _dl_sys.stderr.write("maitux: CALCULATEDLIST start, cl_items=%d\n" % len(cl_items))
    for _dl in cl_items:
        _dl_sys.stderr.write("maitux:   cl: kw=%s formula=%s\n" % (_dl.get("keyword","?"), _dl.get("formula","")[:80]))
    _dl_sys.stderr.write("maitux:   list_arrays=%s\n" % {k:len(v) for k,v in list_arrays.items()})
    _dl_sys.stderr.write("maitux:   str_arrays=%s\n" % {k:len(v) for k,v in str_arrays.items()})
    _dl_sys.stderr.write("maitux:   calc_scalars=%s\n" % {k:v for k,v in calc_scalars.items()})
    _dl_sys.stderr.flush()
    if not cl_items:
        return

    # Collect cross-referenceable sibling data for LOOKUP
    sibling_data = _collect_cross_referenceable_data(self)
    _LOOKUP = _make_lookup(sibling_data)

    # Scope-safe eval globals
    _TOKEN_RE = re.compile(r'\[([A-Za-z_]\w*)\]')
    # GROUP aggregation helpers: parallel-arrays grouped by key
    #
    # Missing-value policy: a non-numeric or empty cell is SKIPPED and the
    # aggregate is computed from the survivors, so one failed injection does
    # not blank out a whole group.  The surviving n is therefore implicit --
    # COUNT() on the report is what keeps it auditable.
    #
    # A group with nothing numeric left has nothing to compute, so it yields
    # the '---' placeholder instead of a fabricated 0.0.  P1 removed the
    # downstream None-filter, so a placeholder no longer shifts index
    # alignment against the sibling arrays.
    def _num_or_none(v):
        """Coerce to float, or None when the cell is missing / not numeric."""
        if v is None:
            return None
        if isinstance(v, bool):
            return float(v)
        if isinstance(v, (int, float)):
            return float(v)
        try:
            if isinstance(v, str):
                v = v.decode("utf-8", "replace")
            s = unicode(v).strip()
            if not s:
                return None
            return float(s)
        except (ValueError, TypeError):
            return None

    def _nums_only(seq):
        """The numeric survivors of seq, in order."""
        return [x for x in (_num_or_none(v) for v in seq) if x is not None]

    def _norm_key(k):
        """Normalise a group key to unicode so CJK keys compare correctly."""
        if isinstance(k, str):
            k = k.decode("utf-8", "replace")
        return unicode(k) if k is not None else u""

    def _group_apply(values, key_arrays, agg, empty=_PLACEHOLDER):
        """Group by key, aggregate the survivors, broadcast to input length.

        key_arrays is a tuple of parallel key columns.  The group key is
        the tuple of their normalised values, so several columns combine
        into one composite key -- e.g. (impurity name, spike level).  A
        single key column yields a one-element tuple, which groups exactly
        as the earlier single-key form did, so existing formulas are
        unaffected."""
        rows = list(zip(values, *key_arrays))

        def _key(row):
            return tuple(_norm_key(k) for k in row[1:])

        groups = {}
        for row in rows:
            groups.setdefault(_key(row), []).append(_num_or_none(row[0]))
        out = {}
        for k, vals in groups.items():
            nums = [x for x in vals if x is not None]
            out[k] = agg(nums) if nums else empty
        return [out[_key(row)] for row in rows]

    def _agg_stdev(nums):
        """Sample standard deviation.

        Fewer than two values leaves it undefined, so return the '---'
        placeholder.  Returning 0.0 there would read as `perfect
        precision` on a validation report."""
        n = len(nums)
        if n < 2:
            return _PLACEHOLDER
        mean = sum(nums) / n
        import math as _gs_math
        return _gs_math.sqrt(sum((v - mean) ** 2 for v in nums) / (n - 1))

    # Scalar versions: ignore grouping, return single global value
    def _group_avg(values, *keys):
        nums = _nums_only(values)
        return sum(nums) / len(nums) if nums else _PLACEHOLDER

    def _group_sum(values, *keys):
        # An empty sum is 0 mathematically, but on a report a 0 that
        # came from no data at all is indistinguishable from a real
        # measured 0.  Match the siblings and say '---'.
        nums = _nums_only(values)
        return sum(nums) if nums else _PLACEHOLDER

    def _group_max(values, *keys):
        nums = _nums_only(values)
        return max(nums) if nums else _PLACEHOLDER

    def _group_min(values, *keys):
        nums = _nums_only(values)
        return min(nums) if nums else _PLACEHOLDER

    # Two-sided 95% Student t, keyed by degrees of freedom (n - 1).
    # Exact table values only: an approximation here would produce a
    # confidence interval that looks right and is not.  A degrees-of-
    # freedom value outside the table is reported, never guessed.
    _T_95 = {
        1: 12.706205, 2: 4.302653, 3: 3.182446, 4: 2.776445,
        5: 2.570582, 6: 2.446912, 7: 2.364624, 8: 2.306004,
        9: 2.262157, 10: 2.228139,
    }

    def _agg_rsd(nums):
        """Relative standard deviation, in percent."""
        if len(nums) < 2:
            return _PLACEHOLDER
        mean = sum(nums) / len(nums)
        if mean == 0:
            return _PLACEHOLDER
        return _agg_stdev(nums) / mean * 100.0

    def _agg_ci(nums, sign):
        """One bound of the two-sided 95% confidence interval of the mean.

        n comes from the group itself, so groups of different sizes each
        get their own t value.  Hard-coding one group's n would silently
        use the wrong t for every differently sized group."""
        n = len(nums)
        if n < 2:
            return _PLACEHOLDER
        t = _T_95.get(n - 1)
        if t is None:
            import sys as _ci_sys
            _ci_sys.stderr.write(
                "maitux:   CI: no t value for df=%d (n=%d); table covers df 1-10\n" % (n - 1, n))
            return _PLACEHOLDER
        sd = _agg_stdev(nums)
        import math as _ci_math
        return sum(nums) / n + sign * t * sd / _ci_math.sqrt(n)

    # List versions: per-group aggregate broadcast to input length.
    # Every one takes *keys, so a formula may group by one column or by
    # several combined -- GROUP_AVGlist([rec], [name], [level]).
    def _group_avglist(values, *keys):
        return _group_apply(values, keys, lambda ns: sum(ns) / len(ns))

    def _group_sumlist(values, *keys):
        return _group_apply(values, keys, sum)

    def _group_maxlist(values, *keys):
        return _group_apply(values, keys, max)

    def _group_minlist(values, *keys):
        return _group_apply(values, keys, min)

    def _group_stdevlist(values, *keys):
        """Per-group standard deviation, broadcast to input length."""
        return _group_apply(values, keys, _agg_stdev)

    def _group_countlist(values, *keys):
        """How many numeric values survived in each group.

        The counterpart of COUNT_ROWS for the grouped statistics.  Missing
        values are skipped by GROUP_AVG / GROUP_RSD / GROUP_CI_*, which
        makes their n implicit; this is what makes it auditable.  An empty
        group counts 0, not '---'."""
        return _group_apply(values, keys, len, empty=0)

    def _group_rsdlist(values, *keys):
        """Per-group RSD in percent, broadcast to input length."""
        return _group_apply(values, keys, _agg_rsd)

    def _group_ci_lowlist(values, *keys):
        """Lower bound of each group's 95% CI, broadcast to input length."""
        return _group_apply(values, keys, lambda ns: _agg_ci(ns, -1))

    def _group_ci_highlist(values, *keys):
        """Upper bound of each group's 95% CI, broadcast to input length."""
        return _group_apply(values, keys, lambda ns: _agg_ci(ns, +1))

    # ---- rounding, formatting, numeric-isation -------------------------
    #
    # These four are SCALAR functions on the per-element path and must not
    # be added to _ARRAY_FN_RE.  Rounding is kept out of RESULT_STATUS /
    # RESULT_NUM on purpose: a precision change should touch a formula, not
    # a core calculation function.

    def _dec_quantize(val, digits, rounding):
        """Quantize to `digits` decimals with an explicit rounding mode.

        Returns a Decimal, or None when the input is not a number.  The
        float is converted through repr() so the decimal the analyst
        actually typed is what gets rounded -- Decimal(float) would round
        the binary expansion instead."""
        from decimal import Decimal, InvalidOperation
        n = _num_or_none(val)
        if n is None:
            return None
        try:
            d = int(digits)
        except (ValueError, TypeError):
            return None
        try:
            q = Decimal(1).scaleb(-d)
            return Decimal(repr(n)).quantize(q, rounding=rounding)
        except (InvalidOperation, ValueError, ArithmeticError):
            return None

    def _round_half_up(val, digits=0):
        """Round half away from zero.  Returns a NUMBER."""
        if isinstance(val, list):
            return [_round_half_up(v, digits) for v in val]
        from decimal import ROUND_HALF_UP
        d = _dec_quantize(val, digits, ROUND_HALF_UP)
        return _PLACEHOLDER if d is None else float(d)

    def _round_half_even(val, digits=0):
        """Round half to even -- GB/T 8170 / ChP numeric rounding.

        Differs from _round_half_up only on an exact half: the retained
        digit goes to the even side.  Returns a NUMBER."""
        if isinstance(val, list):
            return [_round_half_even(v, digits) for v in val]
        from decimal import ROUND_HALF_EVEN
        d = _dec_quantize(val, digits, ROUND_HALF_EVEN)
        return _PLACEHOLDER if d is None else float(d)

    def _format_digits(val, digits=0):
        """Fixed number of decimals, TRAILING ZEROS KEPT.  Returns a STRING.

        Rounds the same way ROUND does, so the two never disagree on the
        digits they show.  Being a string, the result cannot be referenced
        by a downstream numeric formula (ISSUE-003) -- point later formulas
        at the ROUND field, and use FORMAT only for final display."""
        if isinstance(val, list):
            return [_format_digits(v, digits) for v in val]
        from decimal import ROUND_HALF_UP
        d = _dec_quantize(val, digits, ROUND_HALF_UP)
        return _PLACEHOLDER if d is None else unicode(d)

    # Markers that genuinely contribute zero to a total: a result below the
    # limit of quantification is known to be near zero.  Anything else
    # non-numeric is an UNKNOWN contribution, not a zero one, and must not
    # be silently summed as 0.
    _ZERO_MARKERS = frozenset([
        u"", u"N.D.", u"ND", u"N.D", u"<LOQ", u"< LOQ", u"<LOD", u"< LOD",
    ])

    def _result_num(value, name=None, main_name=None):
        """The numeric contribution of ONE row.  Scalar, per-element.

        main component (name == main_name) -> 0
        below-limit marker / empty            -> 0
        a number                             -> that number
        anything else non-numeric            -> '---'

        Per-element by design: RESULT_STATUS now returns a mixed array, so
        the type has to be judged one row at a time."""
        if isinstance(value, list) or isinstance(name, list) \
                or isinstance(main_name, list):
            # A list here means the formula landed on the array path, which
            # this scalar signature cannot serve.  Say so instead of
            # quietly computing row 1 and broadcasting it to every row.
            import sys as _rn_sys
            _rn_sys.stderr.write(
                "maitux:   RESULT_NUM got an array argument -- it is a per-element function; split the formula into two fields\n")
            return _PLACEHOLDER
        if name is not None and main_name is not None:
            if _norm_key(name).strip() == _norm_key(main_name).strip():
                return 0
        n = _num_or_none(value)
        if n is not None:
            return n
        if _norm_key(value).strip().upper() in _ZERO_MARKERS:
            return 0
        return _PLACEHOLDER

    # ---- elapsed time ---------------------------------------------------
    #
    # Month names are matched against a table on purpose.  %B parses
    # through the C locale, so a timestamp that reads fine on one
    # deployment raises on another with a different LANG -- and the
    # failure would surface only as an empty field (ISSUE-007).
    _MONTHS = {
        u"JAN": 1, u"FEB": 2, u"MAR": 3, u"APR": 4,
        u"MAY": 5, u"JUN": 6, u"JUL": 7, u"AUG": 8,
        u"SEP": 9, u"OCT": 10, u"NOV": 11, u"DEC": 12,
    }

    # 'May 12, 2026 1:00:00 PM CST'  -- how SENAITE renders a datetime
    _TIME_NAMED_RE = re.compile(
        r'^\s*([A-Za-z]{3,})\.?\s+(\d{1,2})\s*,?\s+(\d{4})\s+'
        r'(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([AaPp][Mm])?\.?\s*'
        r'([\w+:\-]*)\s*$')

    # '2026-05-12 13:00:00 CST' / '2026-05-12T13:00:00+08:00'
    _TIME_ISO_RE = re.compile(
        r'^\s*(\d{4})-(\d{1,2})-(\d{1,2})[ T](\d{1,2}):(\d{2})'
        r'(?::(\d{2}))?\s*([\w+:\-]*)\s*$')

    def _parse_dt(value):
        """Parse a timestamp into (datetime, timezone_label).

        Returns (None, None) when the text is not a timestamp."""
        import datetime as _pd_dt
        if value is None:
            return None, None
        t = _safe_text(value).strip()
        if not t:
            return None, None
        m = _TIME_NAMED_RE.match(t)
        if m:
            mon = _MONTHS.get(m.group(1)[:3].upper())
            if mon is None:
                return None, None
            day, year = int(m.group(2)), int(m.group(3))
            hh, mm = int(m.group(4)), int(m.group(5))
            ss = int(m.group(6) or 0)
            ap = (m.group(7) or u"").upper()
            if ap == u"PM" and hh != 12:
                hh += 12
            elif ap == u"AM" and hh == 12:
                hh = 0
            tz = (m.group(8) or u"").strip().upper()
            try:
                return _pd_dt.datetime(year, mon, day, hh, mm, ss), tz
            except ValueError:
                return None, None
        m = _TIME_ISO_RE.match(t)
        if m:
            try:
                dt = _pd_dt.datetime(
                    int(m.group(1)), int(m.group(2)), int(m.group(3)),
                    int(m.group(4)), int(m.group(5)), int(m.group(6) or 0))
            except ValueError:
                return None, None
            return dt, (m.group(7) or u"").strip().upper()
        return None, None

    def _time_elapsed_hours(times, digits=1, base=None):
        """Hours since a reference moment, one per row.

        Without `base`, t0 is the earliest timestamp in the array itself, so
        the earliest row reads 0.  With `base` -- typically a timestamp
        looked up from another analysis -- that becomes t0 instead:

            TIME_ELAPSED_HOURS([imp_qc_inj_time], 1, [imp_std1_inj_lookup])

        which is what a stability series actually measures: hours since the
        reference standard was injected, not since the first QC point.  The
        two differ by a constant, so getting it wrong offsets the whole
        column while every value still looks plausible.

        A row earlier than t0 yields a NEGATIVE number, deliberately.  It
        says an injection was recorded before the reference it is measured
        from, which cannot happen in the lab -- so it is a data-entry error,
        and blanking it or clamping it to zero would hide the one thing
        worth seeing.  Every such row is named in the log.

        A `base` that cannot be parsed returns "---" rather than quietly
        falling back to the array minimum.  Silently switching t0 would
        produce a series measured from the wrong moment that reads as
        perfectly ordinary.

        Inconsistent timezone labels are refused rather than subtracted:
        across a daylight-saving change the same wall-clock difference is
        not the same elapsed time (ISSUE-007).  `base` is held to the same
        rule as the array."""
        import sys as _te_sys
        if isinstance(digits, (list, tuple)):
            digits = digits[0] if digits else 1
        if isinstance(base, (list, tuple)):
            base = base[0] if base else None
        if not isinstance(times, (list, tuple)):
            times = [times]
        parsed = [_parse_dt(t) for t in times]
        labels = set(z for dt, z in parsed if dt is not None)

        base_dt = None
        if base not in (None, "", u"", _PLACEHOLDER):
            base_dt, base_label = _parse_dt(base)
            if base_dt is None:
                _te_sys.stderr.write(
                    "maitux:   TIME_ELAPSED_HOURS: base %r is not a parsable "
                    "timestamp -- refusing to fall back to the array "
                    "minimum\n" % (base,))
                return [_PLACEHOLDER] * len(times)
            labels.add(base_label)

        if len(labels) > 1:
            _te_sys.stderr.write(
                "maitux:   TIME_ELAPSED_HOURS: inconsistent timezone labels %s -- refusing to subtract\n"
                % sorted(labels))
            return [_PLACEHOLDER] * len(times)
        valid = [dt for dt, z in parsed if dt is not None]
        if not valid:
            _te_sys.stderr.write(
                "maitux:   TIME_ELAPSED_HOURS: no parsable timestamp in %d value(s)\n" % len(times))
            return [_PLACEHOLDER] * len(times)
        t0 = base_dt if base_dt is not None else min(valid)
        out = []
        negatives = []
        for index in range(len(parsed)):
            dt, z = parsed[index]
            if dt is None:
                out.append(_PLACEHOLDER)
                continue
            d = dt - t0
            hours = (d.days * 86400.0 + d.seconds
                     + d.microseconds / 1000000.0) / 3600.0
            if hours < 0:
                negatives.append((index + 1, times[index]))
            out.append(_round_half_up(hours, digits))
        if negatives:
            from bika.lims import logger as _te_logger
            _te_logger.warn(
                "maitux.calcenhance: TIME_ELAPSED_HOURS on %s produced %d "
                "negative hour(s): %s. Those rows are timestamped BEFORE "
                "the reference (%s), which cannot happen -- check the "
                "entered times."
                % (getattr(self, "id", "?"), len(negatives),
                   ", ".join("row %d = %r" % (n, v) for n, v in negatives),
                   ("base %r" % (base,)) if base_dt is not None
                   else "the earliest row"))
        return out

    def _coalesce_conflict(row_index, chosen, disagreeing):
        """Report a row whose sources disagree.  Never resolves it."""
        from bika.lims import logger as _co_logger
        _co_logger.warn(
            "maitux.calcenhance: COALESCE on %s row %s found more than "
            "one source with a value: kept %r (the first argument wins) "
            "and ignored %r -- decide which source is authoritative"
            % (getattr(self, "id", "?"),
               "-" if row_index is None else row_index + 1,
               chosen, disagreeing))

    def _shift(values, offset=-1):
        """One row up or down the same column.

            SHIFT([col], -1)   the NEXT row's value (look down)
            SHIFT([col], +1)   the PREVIOUS row's value (look up)

        Written for the separation table, where resolution-to-next-peak
        is resolution-to-previous-peak read one row down:

            imp_sep_res_after = SHIFT([imp_sep_res_before], -1)

        Rows that fall outside the column yield the "---" placeholder,
        never 0.  "There is no next peak" and "the resolution is zero"
        are different statements, and a limit check must not read one as
        the other.

        An array-path function: it needs the whole column, since a
        per-element view cannot see the neighbouring row.
        """
        import sys as _sh_sys
        if isinstance(offset, (list, tuple)):
            offset = offset[0] if offset else -1
        try:
            offset = int(offset)
        except (ValueError, TypeError):
            _sh_sys.stderr.write(
                "maitux:   SHIFT: offset %r is not a whole number\n"
                % (offset,))
            offset = -1
        if not isinstance(values, (list, tuple)):
            values = [values]
        count = len(values)
        results = []
        for index in range(count):
            source = index - offset
            if source < 0 or source >= count:
                results.append(_PLACEHOLDER)
            else:
                results.append(values[source])
        return results

    def _coalesce(*cols):
        """First present value per row, across the given columns.

        For a keyword that has to be read from two different analyses --
        a purity living on the main-component reference standard for one
        row and on the impurity standard for the next.  Each LOOKUP
        yields "---" for the rows it cannot match, and this keeps
        whichever one answered:

            COALESCE([purity_main], [purity_impurity])

        Argument order is the declared precedence.  A row where more
        than one source has a DIFFERENT value is a data conflict, not a
        preference: the first still wins, but it is logged instead of
        being resolved quietly.
        """
        if not cols:
            return _MISSING
        if not any(isinstance(c, (list, tuple)) for c in cols):
            chosen, disagreeing = _coalesce_pick(list(cols))
            if disagreeing:
                _coalesce_conflict(None, chosen, disagreeing)
            return chosen
        width = 0
        for c in cols:
            if isinstance(c, (list, tuple)):
                width = max(width, len(c))
        results = []
        for index in range(width):
            row = []
            for c in cols:
                if isinstance(c, (list, tuple)):
                    row.append(c[index] if index < len(c) else None)
                else:
                    row.append(c)
            chosen, disagreeing = _coalesce_pick(row)
            if disagreeing:
                _coalesce_conflict(index, chosen, disagreeing)
            if isinstance(chosen, _Missing):
                results.append(_PLACEHOLDER)
            else:
                results.append(chosen)
        return results

    def _result_status(values, loq=None, lod=None):
        """Element-wise LOQ/LOD status: >=LOQ→numeric, >=LOD→'<LOQ', <LOD→'N.D.'
        When loq/lod omitted (or None), auto-read from AS Limits tab.
        """
        # Auto-read from AS Limits if not explicitly provided
        if loq is None:
            try:
                service = self.getAnalysisService()
                loq = float(service.getLowerLimitOfQuantification() or 0)
            except Exception:
                loq = 0
        if lod is None:
            try:
                service = self.getAnalysisService()
                lod = float(service.getLowerDetectionLimit() or 0)
            except Exception:
                lod = 0
        # Unwrap scalar args from GROUP-like expansion ([val] → val)
        if isinstance(loq, list):
            loq = loq[0] if loq else 0
        if isinstance(lod, list):
            lod = lod[0] if lod else 0
        results = []
        for v in values:
            if v is None or v == u"" or v == "":
                results.append(u"\u2014")  # em dash
                continue
            try:
                fv = float(v)
            except (ValueError, TypeError):
                results.append(u"\u2014")
                continue
            import math
            if math.isnan(fv):
                results.append(u"\u2014")
            elif fv >= loq:
                # Pass the number through untouched.  Formatting used to
                # be hardcoded here as "%.4f", which (a) forced every AS to
                # four decimals regardless of its own significant-figure
                # requirement, and (b) turned the whole column into strings,
                # so no downstream formula could compute with it.  Rounding
                # is ROUND / ROUND_EVEN's job and display is FORMAT's.
                results.append(fv)
            elif fv >= lod:
                results.append(u"<LOQ")
            else:
                results.append(u"N.D.")
        return results

    def _index_by(target_arr, key_arr, match_val):
        """Look up a value in this AS by matching a key column.

        Both arrays arrive already inlined by the calling engine's
        INDEX_BY rewrite, so this only ever sees real sequences.  If it
        does not, the rewrite did not fire and the formula reached the
        per-element path, where each row hands over a single scalar --
        report that plainly rather than iterating a string one character
        at a time and complaining the key is not among its letters."""
        if isinstance(match_val, list):
            match_val = match_val[0] if match_val else None
        if isinstance(target_arr, (str, unicode)) or \
                isinstance(key_arr, (str, unicode)) or \
                not hasattr(target_arr, "__len__") or \
                not hasattr(key_arr, "__len__"):
            import sys as _ibg_sys
            _ibg_sys.stderr.write(
                "maitux:   INDEX_BY: needs two list fields as its first two arguments, got %s and %s -- write it as INDEX_BY([values], [keys], key)\n"
                % (type(target_arr).__name__, type(key_arr).__name__))
            return _PLACEHOLDER

        def _to_u(v):
            if v is None:
                return u""
            if isinstance(v, unicode):
                return v
            if isinstance(v, str):
                return v.decode("utf-8", "replace")
            return unicode(v)

        str_key_arr = [_to_u(v) for v in key_arr]
        sv = _to_u(match_val)
        try:
            idx = str_key_arr.index(sv)
        except ValueError:
            # A key that is not there is missing data, not a crash.  Raising
            # made the whole row fail, and the reason was only ever visible
            # in the container log.
            import sys as _ib_sys
            _ib_sys.stderr.write(
                (u"maitux:   INDEX_BY: key '%s' not in key array %s\n"
                 % (sv, str_key_arr[:6])).encode("utf-8"))
            return _PLACEHOLDER
        try:
            return target_arr[idx]
        except IndexError:
            # key array longer than the target array
            return _PLACEHOLDER

    def _slope(y, x):
        """Linear regression slope by least squares."""
        n = len(y)
        if n < 2:
            return 0.0
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        sum_x2 = sum(xi * xi for xi in x)
        denom = n * sum_x2 - sum_x * sum_x
        if denom == 0:
            return 0.0
        return (n * sum_xy - sum_x * sum_y) / denom

    def _intercept(y, x):
        """Linear regression intercept by least squares."""
        n = len(y)
        if n < 2:
            return 0.0
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        sum_x2 = sum(xi * xi for xi in x)
        denom = n * sum_x2 - sum_x * sum_x
        if denom == 0:
            return 0.0
        return (sum_y * sum_x2 - sum_x * sum_xy) / denom

    def _rsq(y, x):
        """R-squared (coefficient of determination) by least squares."""
        n = len(y)
        if n < 2:
            return 0.0
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        sum_x2 = sum(xi * xi for xi in x)
        sum_y2 = sum(yi * yi for yi in y)
        denom_xy = n * sum_x2 - sum_x * sum_x
        denom_yy = n * sum_y2 - sum_y * sum_y
        if denom_xy == 0 or denom_yy == 0:
            return 0.0
        r = (n * sum_xy - sum_x * sum_y) / (
            (denom_xy ** 0.5) * (denom_yy ** 0.5))
        return r * r

    def _sse(y, x):
        """Residual sum of squares about the least-squares line."""
        n = len(y)
        if n < 2:
            return 0.0
        m = _slope(y, x)
        b = _intercept(y, x)
        return sum((y[i] - (m * x[i] + b)) ** 2 for i in range(n))

    def _rows_regression(func, cols, min_pairs=2):
        """Run func(y, x) once per row over parallel Y/X column lists.

        cols is the flattened *args tuple: the first half are Y columns and
        the second half are X columns (matching SLOPE([y], [x]) arg order).

        Missing cells are skipped and the regression runs on the surviving
        (x, y) pairs -- a calibration series with one failed level still
        has a slope.  A pair needs BOTH coordinates, so a cell missing on
        either axis drops that pair and no other.

        A row yields '---' when it has fewer than min_pairs surviving pairs,
        or (for the regressions) when every surviving point sits at the same
        x -- no line through them is determined, and 0.0 would be a
        fabricated slope."""
        if not cols:
            return []
        n = len(cols)
        if n < 2 or n % 2 != 0:
            # Y and X columns are positional halves, so an odd count means
            # the formula is malformed.  Say so: returning [] silently left
            # the field empty with no hint as to why.
            import sys as _rr_sys
            _rr_sys.stderr.write(
                "maitux:   *_ROWS needs an even column count (half Y, half X); got %d\n" % n)
            return []
        half = n // 2
        y_cols = cols[:half]
        x_cols = cols[half:]

        n_rows = len(y_cols[0])
        results = []
        for i in range(n_rows):
            ys = []
            xs = []
            for yc, xc in zip(y_cols, x_cols):
                yv = _num_or_none(yc[i])
                xv = _num_or_none(xc[i])
                if yv is None or xv is None:
                    continue
                ys.append(yv)
                xs.append(xv)
            if len(ys) < min_pairs:
                results.append(_PLACEHOLDER)
                continue
            if min_pairs >= 2 and len(set(xs)) < 2:
                results.append(_PLACEHOLDER)
                continue
            results.append(func(ys, xs))
        return results

    def _slope_rows(*cols):
        return _rows_regression(_slope, cols)

    def _intercept_rows(*cols):
        return _rows_regression(_intercept, cols)

    def _rsq_rows(*cols):
        """R-squared per row, over at least five surviving levels.

        Two points always sit exactly on their own line, so R-squared would
        read 1.0 and assert perfect linearity from no evidence.  ICH Q2 asks
        for five concentration levels, so fewer than five surviving points
        yields '---' rather than any number."""
        return _rows_regression(_rsq, cols, min_pairs=5)

    def _sse_rows(*cols):
        """Residual sum of squares per row."""
        return _rows_regression(_sse, cols)

    def _count_rows(*cols):
        """How many (x, y) pairs each row actually contributed.

        This is the audit trail for the regressions: with missing cells
        skipped, the n behind a slope or an R-squared is implicit, and this
        is what puts it on the report.  An empty row counts 0 -- unlike a
        statistic, "how many" always has a definite answer."""
        return _rows_regression(lambda ys, xs: len(ys), cols, min_pairs=0)

    def _stdev_rows(*cols):
        """Per-row sample standard deviation over parallel column lists.

        Each column is a List array of equal length; returns a list with one
        sample standard deviation per row index.  Non-numeric cells are
        skipped; a row with no numeric cell at all yields '---'.
        """
        if not cols:
            return []

        def _num(v):
            try:
                if isinstance(v, bool):
                    return float(v)
                if isinstance(v, (int, float)):
                    return float(v)
                if isinstance(v, unicode):
                    s = v
                elif isinstance(v, str):
                    s = v.decode("utf-8", "replace")
                else:
                    s = unicode(v)
                return float(s.strip())
            except (ValueError, TypeError):
                return None

        import math as _stdev_math
        n_rows = len(cols[0])
        results = []
        for i in range(n_rows):
            # Skip the missing cells and use the survivors instead of
            # abandoning the whole row.  An abandoned row used to report
            # 0.0, which on a precision report reads as 'perfect'.
            row = [v for v in (_num(col[i]) for col in cols)
                   if v is not None]
            if len(row) < 2:
                # Fewer than two surviving cells leaves the statistic
                # undefined.  0.0 here would read as 'perfect precision'.
                results.append(_PLACEHOLDER)
                continue
            mean = sum(row) / len(row)
            results.append(
                _stdev_math.sqrt(
                    sum((v - mean) ** 2 for v in row) / (len(row) - 1)))
        return results

    def _rsd_rows(*cols):
        """Per-row percent relative standard deviation (RSD%) over parallel
        column lists.  Rows with any non-numeric cell or fewer than 2 numeric
        cells yield 0.0.
        """
        if not cols:
            return []

        def _num(v):
            try:
                if isinstance(v, bool):
                    return float(v)
                if isinstance(v, (int, float)):
                    return float(v)
                if isinstance(v, unicode):
                    s = v
                elif isinstance(v, str):
                    s = v.decode("utf-8", "replace")
                else:
                    s = unicode(v)
                return float(s.strip())
            except (ValueError, TypeError):
                return None

        import math as _rsd_math
        n_rows = len(cols[0])
        results = []
        for i in range(n_rows):
            # Skip the missing cells and use the survivors instead of
            # abandoning the whole row.  An abandoned row used to report
            # 0.0, which on a precision report reads as 'perfect'.
            row = [v for v in (_num(col[i]) for col in cols)
                   if v is not None]
            if len(row) < 2:
                # Fewer than two surviving cells leaves the statistic
                # undefined.  0.0 here would read as 'perfect precision'.
                results.append(_PLACEHOLDER)
                continue
            mean = sum(row) / len(row)
            if mean == 0:
                # RSD is a ratio to the mean; a zero mean makes it
                # undefined rather than zero.
                results.append(_PLACEHOLDER)
                continue
            sd = _rsd_math.sqrt(
                sum((v - mean) ** 2 for v in row) / (len(row) - 1))
            results.append(sd / mean * 100.0)
        return results

    _SAFE = {"__builtins__": {
        "abs": abs, "max": max, "min": min, "round": round,
        "sum": sum, "len": len, "pow": pow,
        "True": True, "False": False, "None": None,
        "avg": lambda x: sum(x) / len(x) if x else 0,
        "floor": __import__("math").floor,
        "ceil": __import__("math").ceil,
        "sqrt": __import__("math").sqrt,
        "stdev": lambda x: (
            __import__("math").sqrt(
                sum((v - sum(x) / len(x)) ** 2 for v in x) / (len(x) - 1)
            ) if len(x) > 1 else _PLACEHOLDER
        ),
        "log": __import__("math").log,
        "log10": __import__("math").log10,
        "exp": __import__("math").exp,
        "LOOKUP": _LOOKUP,
        "GROUP_AVG": _group_avg,
        "GROUP_SUM": _group_sum,
        "GROUP_MAX": _group_max,
        "GROUP_MIN": _group_min,
        "GROUP_AVGlist": _group_avglist,
        "GROUP_SUMlist": _group_sumlist,
        "GROUP_MAXlist": _group_maxlist,
        "GROUP_MINlist": _group_minlist,
        "GROUP_STDEVlist": _group_stdevlist,
        "GROUP_RSDlist": _group_rsdlist,
        "GROUP_CI_LOWlist": _group_ci_lowlist,
        "GROUP_CI_HIGHlist": _group_ci_highlist,
        "RESULT_STATUS": _result_status,
        "COALESCE": _coalesce,
        "SHIFT": _shift,
        "TIME_ELAPSED_HOURS": _time_elapsed_hours,
        "RESULT_NUM": _result_num,
        "ROUND": _round_half_up,
        "ROUND_EVEN": _round_half_even,
        "FORMAT": _format_digits,
        "INDEX_BY": _index_by,
        "SLOPE": _slope,
        "INTERCEPT": _intercept,
        "RSQ": _rsq,
        "SLOPE_ROWS": _slope_rows,
        "INTERCEPT_ROWS": _intercept_rows,
        "RSQ_ROWS": _rsq_rows,
        "SSE": _sse,
        "SSE_ROWS": _sse_rows,
        "COUNT_ROWS": _count_rows,
        "GROUP_COUNTlist": _group_countlist,
        "STDEV_ROWS": _stdev_rows,
        "RSD_ROWS": _rsd_rows,
    }}

    def _eval_expr(formula, values):
        """Evaluate formula with a flat value dict.
        Array values in 'values' are single scalars (one element at a time).
        """
        # Python 2: work on unicode so CJK values survive
        expr = formula
        if isinstance(expr, str):
            expr = expr.decode("utf-8")
        expr, variables = _bind_formula_values(expr, _TOKEN_RE, values.get)
        # An empty `variables` does not mean there is nothing to compute: a
        # formula made only of literals -- e.g. LOOKUP("as","field","key","R-1")
        # -- is self-contained and must still be evaluated.  Returning None
        # here used to leave every such field permanently empty.
        return eval(expr, _SAFE, variables)

    # INDEX_BY([target], [key], match) resolves to ONE value for the whole
    # column, so substitute the arrays before the path decision -- the same
    # rewrite the scalar engine does (_INDEX_BY_RE).  Without it INDEX_BY
    # reached the per-element path and saw a single scalar per row, which can
    # never match, so the column came out entirely '---'.
    _CL_INDEX_BY_RE = re.compile(
        r'INDEX_BY\s*\(\s*\[([A-Za-z_]\w*)\]\s*,\s*\[([A-Za-z_]\w*)\]\s*,\s*([^)]+)\)')

    def _cl_replace_index_by(match):
        """Rewrite one INDEX_BY call with its array arguments inlined."""
        target_kw, key_kw = match.group(1), match.group(2)
        rest = match.group(3).strip()
        target_arr = list_arrays.get(target_kw)
        if target_arr is None:
            target_arr = str_arrays.get(target_kw)
        key_arr = str_arrays.get(key_kw)
        if key_arr is None:
            key_arr = list_arrays.get(key_kw)
        if target_arr is None or key_arr is None:
            # one of the two is not an array here; leave the formula alone
            # rather than rewrite it into something that cannot work
            _dl_sys.stderr.write(
                "maitux:   INDEX_BY: [%s] or [%s] is not a list field -- left as written\n" % (target_kw, key_kw))
            return match.group(0)
        # a [kw] third argument has to resolve to a scalar to be inlined
        m3 = _TOKEN_RE.match(rest)
        if m3:
            ref = m3.group(1)
            if ref in calc_scalars:
                rest = repr(calc_scalars[ref])
            elif ref in str_arrays and str_arrays[ref]:
                vals = set(str_arrays[ref])
                if len(vals) == 1:
                    rest = repr(list(vals)[0])
                else:
                    # varies by row: there is no single key to look up
                    _dl_sys.stderr.write(
                        "maitux:   INDEX_BY: third argument [%s] varies by row -- left as written\n" % ref)
                    return match.group(0)
            else:
                return match.group(0)
        return "INDEX_BY(%s, %s, %s)" % (repr(target_arr), repr(key_arr), rest)

    changed = False
    # Strip invisible Unicode formatting chars that creep in via copy-paste
    _INVISIBLE_RE = re.compile(
        u'[\u200b\u200c\u200d\u200e\u200f\ufeff\u00ad\u2060\u2061\u2062\u2063\u2064\u202a\u202b\u202c\u202d\u202e\ufffc]'
    )

    for c in cl_items:
        kw = c.get("keyword", "")
        formula = c.get("formula", "") or ""
        # Restricted to one run by the ordered driver; the arrays
        # collected above still cover every field.
        if only is not None and kw not in only:
            continue
        # Sanitize: remove invisible formatting characters
        if isinstance(formula, str):
            formula = formula.decode("utf-8", "replace")
        formula = _INVISIBLE_RE.sub(u"", formula)

        # Inline any INDEX_BY arrays first.  This also removes those two
        # keywords from the dependency set below, so the looked-up arrays no
        # longer have to share the output column's row count.
        if "INDEX_BY" in formula:
            formula = _CL_INDEX_BY_RE.sub(_cl_replace_index_by, formula)

        # Identify deps: array (List/CalculatedList) vs scalar (Calculated/plain)
        all_refs = [
            m.group(1) for m in _TOKEN_RE.finditer(formula)
            if m.group(1) != kw
        ]
        array_refs = [r for r in all_refs if r in list_arrays]
        str_refs = [r for r in all_refs if r in str_arrays]
        all_array_refs = array_refs + str_refs  # for length validation
        scalar_refs = [r for r in all_refs if r not in list_arrays and r not in str_arrays]

        _dl_sys.stderr.write("maitux:   processing cl kw=%s all_refs=%s array_refs=%s scalar_refs=%s all_array_refs=%s\n" % (
            kw, all_refs, array_refs, scalar_refs, all_array_refs))
        if not all_array_refs:
            # No array deps -- single evaluation, store as [result]
            svm = {}
            for ref_kw in scalar_refs:
                svm[ref_kw] = calc_scalars.get(ref_kw)
            # A bare `except: pass` here meant a failed formula kept the
            # field's previous value -- the stale-value problem P1.6 fixed
            # in the other branches.  A string result (the '---' marker)
            # also used to blow up on float() and land in that silence.
            try:
                r = _eval_expr(formula, svm)
            except Exception as _nad_err:
                _dl_sys.stderr.write(
                    "maitux:   no-array-dep eval FAIL kw=%s: %s\n"
                    % (kw, _nad_err))
                r = None
            if r is None:
                out_val = _PLACEHOLDER
            elif isinstance(r, (str, unicode)):
                out_val = r
            else:
                try:
                    out_val = float(r)
                except (ValueError, TypeError):
                    out_val = _PLACEHOLDER
            new_value = _jj.dumps([out_val])
            if not _same_value(c.get("value", ""), new_value):
                c["value"] = new_value
                changed = True
            continue

        # All referenced arrays (numeric + string) must have the same length
        lens = set()
        for r in all_array_refs:
            if r in list_arrays:
                lens.add(len(list_arrays[r]))
            elif r in str_arrays:
                lens.add(len(str_arrays[r]))
        if len(lens) != 1:
            _dl_sys.stderr.write("maitux:   SKIP kw=%s: mismatched lens=%s\n" % (kw, lens))
            continue  # mismatched lengths -- skip

        n = list(lens)[0]
        _dl_sys.stderr.write("maitux:   eval kw=%s n=%d\n" % (kw, n))
        element_results = []

        # Detect formulas that need full arrays (GROUP_*, RESULT_STATUS)
        # Naming convention: GROUP_* / GROUP_*list / *_ROWS always take the
        # array path.  TIME_ELAPSED_HOURS matches none of those patterns and
        # must stay listed explicitly (ISSUE-007), or it degrades to the
        # per-element path and silently sees one scalar at a time.
        # COALESCE must be here, not on the per-element path: that path
        # short-circuits a whole row to "---" as soon as ANY input is
        # the placeholder, and tolerating missing inputs is precisely
        # what COALESCE is for.
        _ARRAY_FN_RE = re.compile(
            r'(GROUP_\w+(?:list)?|\w+_ROWS|RESULT_STATUS|TIME_ELAPSED_HOURS|COALESCE|SHIFT)\s*\(')
        if _ARRAY_FN_RE.search(formula):
            expr = formula
            if isinstance(expr, str):
                expr = expr.decode("utf-8")
            for ref_kw in all_refs:
                if ref_kw in list_arrays:
                    arr = list_arrays[ref_kw]
                elif ref_kw in str_arrays:
                    arr = str_arrays[ref_kw]
                else:
                    # Pad to the row count.  An empty or absent column
                    # used to be inlined as a SINGLE-element list, while
                    # *_ROWS indexes every column up to the length of the
                    # first one -- so one unused level (imp_lin_a7 = [] on
                    # a two-row linearity series) raised IndexError and
                    # killed the whole regression, even though the row
                    # logic already knows how to skip missing cells.
                    # Padding a real scalar is harmless: callers that
                    # want a scalar read element 0 (RESULT_STATUS's
                    # loq/lod), and a per-row key column repeated is
                    # exactly what a scalar key means.
                    arr = [calc_scalars.get(ref_kw)] * n
                placeholder = "[%s]" % ref_kw
                expr = expr.replace(placeholder, repr(arr))
            try:
                r = eval(expr, _SAFE, {})
                if isinstance(r, list):
                    # Mixed arrays (numeric + string) are legal: a column may
                    # carry a value on one row and a '<LOQ' / 'N.D.' marker on
                    # the next.  Never type the whole column from r[0], and
                    # never drop None -- that would shift every later row's
                    # index against the sibling arrays.  Pure string arrays go
                    # to str_arrays; numeric and mixed arrays are registered
                    # into list_arrays by the check further down.
                    if r and all(isinstance(v, (str, unicode)) for v in r):
                        str_arrays[kw] = r
                    element_results = r
                elif r is not None:
                    element_results = [float(r)]
            except Exception as _dle:
                _dl_sys.stderr.write("maitux:   ARRAY_FN eval FAIL kw=%s: %s\n" % (kw, _dle))
                # Emit one placeholder per row rather than nothing: an
                # empty result is never written, which would leave the
                # previously computed value on display even though it no
                # longer follows from the current inputs.
                element_results = [_PLACEHOLDER] * n
        else:
            for i in range(n):
                svm = {}  # scalar value map for this element
                for ref_kw in array_refs:
                    svm[ref_kw] = list_arrays[ref_kw][i]
                for ref_kw in str_refs:
                    svm[ref_kw] = str_arrays[ref_kw][i]
                for ref_kw in scalar_refs:
                    svm[ref_kw] = calc_scalars.get(ref_kw)
                # "---" placeholder propagation: a row whose inputs contain the
                # method-B "not found" marker yields "---" itself, keeping the
                # row aligned in downstream arrays instead of dropping it.
                if _PLACEHOLDER in svm.values():
                    element_results.append(_PLACEHOLDER)
                    continue
                # Every row must fill its slot.  Appending nothing on
                # failure shortened the array, which shifted every later
                # row against the sibling arrays -- and a short array that
                # came out empty was not written at all, leaving the
                # previous (now stale) value on display.
                try:
                    r = _eval_expr(formula, svm)
                    if r is None:
                        element_results.append(_PLACEHOLDER)
                    elif isinstance(r, (str, unicode)):
                        element_results.append(r)
                    else:
                        element_results.append(float(r))
                except Exception as _dle:
                    _dl_sys.stderr.write("maitux:   eval[%d] FAIL: %s svm=%s\n" % (i, _dle, svm))
                    element_results.append(_PLACEHOLDER)

        _dl_sys.stderr.write("maitux:   result kw=%s element_results=%s (len=%d)\n" % (kw, element_results[:5], len(element_results)))

        if element_results:
            new_value = _jj.dumps(element_results)
            if not _same_value(c.get("value", ""), new_value):
                c["value"] = new_value
                changed = True
            # Update list_arrays for downstream calculatedlist deps.  Numeric
            # and mixed (numeric + "---") arrays are indexable by downstream
            # element-wise formulas; pure string arrays stay in str_arrays.
            if element_results and any(
                    not isinstance(v, (str, unicode)) for v in element_results):
                list_arrays[kw] = element_results

    if changed:
        self.setInterimFields(interims)
