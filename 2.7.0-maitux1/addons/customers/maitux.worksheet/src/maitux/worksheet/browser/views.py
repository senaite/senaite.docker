# -*- coding: utf-8 -*-

import ast
import collections
import json

from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from bika.lims import api
from bika.lims.api.analysis import is_out_of_range
from senaite.core.browser.worksheets.worksheet.analyses_listing import (
    AnalysesView as WorksheetAnalysesView,
)

# Sentinel: tells "decoded to None" apart from "could not be decoded".
_UNPARSEABLE = object()

# Guards the unwrapping below against pathological data.  Real values are one
# level deep; anything past a handful of levels is corruption, not data.
_MAX_UNWRAP_DEPTH = 8


def _decode_scalar(text):
    """Decode one layer of an encoded interim value.

    Accepts JSON as well as the Python repr form (``[u'2']``) that reaches the
    interim fields through the XLSX setup import.  Returns ``_UNPARSEABLE``
    when the text is a plain value rather than an encoded structure.
    """
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError, TypeError, MemoryError):
        return _UNPARSEABLE


def _flatten_encoded(items, depth=0):
    """Replace elements that are themselves encoded lists by their contents.

    ``['["2"]', '["2"]']`` -> ``["2", "2"]``.  Elements that merely look like
    text are left untouched, so a solvent named "[control]" survives.
    """
    if depth >= _MAX_UNWRAP_DEPTH:
        return items
    out = []
    for element in items:
        candidate = element
        if isinstance(candidate, bytes):
            candidate = candidate.decode("utf-8", "replace")
        if isinstance(candidate, basestring):  # noqa: F821  (Python 2 only)
            stripped = candidate.strip()
            # Only try to decode things shaped like an encoded list; a bare
            # numeric string must stay the single value the analyst typed.
            if stripped.startswith("[") and stripped.endswith("]"):
                decoded = _decode_scalar(stripped)
                if isinstance(decoded, list):
                    out.extend(_flatten_encoded(decoded, depth + 1))
                    continue
        out.append(element)
    return out


class GroupedRenderingMixin(object):
    """AS-Grouped rendering, independent of where the analyses come from.

    Everything here works off the item dicts produced by
    AnalysesView.folderitems(), so it applies unchanged to a worksheet
    (analyses of many samples for one service) and to a sample (analyses of
    one sample across many services).  Only the *source* of the analyses
    differs, and that lives in the concrete listing base class.

    Structure: AS -> Sample -> analysis items -> display_rows (list-expanded)
    """

    # ZPT for the table-only rendering (used by contents_table() when embedded
    # inside manage_results).  Does NOT include the master macro.
    as_grouped_table = ViewPageTemplateFile("templates/as_grouped_table.pt")

    def __init__(self, context, request):
        super(GroupedRenderingMixin, self).__init__(context, request)
        self._as_groups = None
        self._raw_interims = {}

    def _raw_interim_values(self, item):
        """Interim values as *stored*, keyed by keyword.

        senaite.core swaps the value for its formatted display text the moment
        an analysis stops being editable:

            # bika/lims/browser/analyses/view.py, _folder_item_calculation
            if not is_editable:
                # Display the text instead of the value
                interim_field["value"] = interim_formatted

        That is deliberate, and right for the native listing: with no input to
        fill there is nothing to round-trip, so a plain string is what the
        React grid wants.  Here it is destructive.  A list interim arrives as
        "a, b, c" instead of '["a","b","c"]', _to_array() can only read that as
        a single element, and the sample block collapses from one row per
        element down to one row -- the layout's whole purpose, lost exactly
        when the results are being reviewed.

        The persistent value is untouched, so read it back off the object.
        One fetch per analysis (api.get_object is cheap on a UID and the
        native view has already woken the object anyway), cached per request
        because every list column asks the same question.
        """
        uid = item.get("uid", "")
        if not uid:
            return {}
        cached = self._raw_interims.get(uid)
        if cached is None:
            cached = {}
            try:
                obj = api.get_object(uid)
                for ifield in (obj.getInterimFields() or []):
                    keyword = ifield.get("keyword", "")
                    if keyword:
                        cached[keyword] = ifield.get("value", "")
            except Exception:
                # A missing or unreadable object must not take the page down;
                # the item value is still there to fall back on.
                cached = {}
            self._raw_interims[uid] = cached
        return cached

    def _get_list_array(self, item, keyword):
        """Elements of a list-type interim, taken from the stored value.

        Falls back to the item value so a keyword the object does not carry
        (or an object that could not be read) behaves as it did before.
        """
        raw = self._raw_interim_values(item)
        if keyword in raw:
            return self._to_array(raw[keyword])
        return self._to_array(self._get_item_field_value(item, keyword))

    def _get_as_sort_key(self, item):
        """Return sort key for the AS (Analysis Service).

        Uses the service_uid from the analysis item to look up the
        AnalysisService object directly.
        """
        service_uid = item.get("service_uid", "")
        if service_uid:
            try:
                service = api.get_object_by_uid(service_uid)
                if service is not None:
                    sk = service.getSortKey()
                    if sk is not None:
                        return sk
            except Exception:
                pass
        return 9999

    # ------------------------------------------------------------------
    # Interim field helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_locked(ifield):
        """Whether an interim is flagged as locked in the Calculation config.

        Locked interims hold instrument-acquired data: maitux.calcenhance
        rejects any write to them that would change a captured value, so they
        must not be offered as editable here either.  The flag is a real bool
        from the Dexterity schema but a string from the Archetypes subfield and
        from XLSX import.
        """
        flag = ifield.get("locked", False)
        if isinstance(flag, bool):
            return flag
        try:
            return str(flag).strip().lower() in (
                "true", "1", "yes", "on", "x")
        except Exception:
            return False

    @staticmethod
    def _is_hidden(ifield):
        """Check if an interim field dict has hidden=True."""
        hidden = ifield.get("hidden", False)
        if isinstance(hidden, bool):
            return hidden
        return str(hidden).lower() in ("true", "1", "yes")

    @staticmethod
    def _get_render_type(ifield):
        """Return the render type for an interim field.

        Possible values:
          - "numeric"   : editable number input
          - "multivalue": editable list (MultiValue)
          - "readonly"  : calculated scalar (ReadonlyField)
          - "readonlylist": calculated list (readonly MultiValue)
        """
        rt = ifield.get("result_type", "")
        orig = ifield.get("_orig_result_type", "")

        # A locked interim (instrument-acquired data) is never hand-editable.
        # maitux.calcenhance refuses the write server-side anyway; rendering it
        # read-only keeps the form honest about it.
        if AnalysesGroupedView._is_locked(ifield):
            base = orig or rt
            if base in ("list", "calculatedlist", "multivalue"):
                return "readonlylist"
            return "readonly"

        # maitux.calcenhance rewrites calculatedlist to "multivalue" so the
        # native ReactJS listing picks the MultiValue widget for it; the real
        # type only survives in _orig_result_type.  It has to be consulted
        # first, otherwise a computed list is indistinguishable from a
        # hand-entered one and would be rendered as editable.
        if orig == "calculatedlist":
            return "readonlylist"
        if orig == "calculated":
            return "readonly"

        if rt == "multivalue":
            return "multivalue"
        if rt == "readonly":
            return "readonly"
        return "numeric"

    @staticmethod
    def _get_item_field_value(item, keyword):
        """Extract the display value for an interim field on an item.

        Handles the dict-wrapped values from maitux.calcenhance patches:
          - scalar : item[kw] = value
          - list   : item[kw] = {"value": [...], "result_type": "multivalue"}
          - readonly : item[kw] = {"result_type": "readonly", "value": ...}
        """
        val = item.get(keyword)
        if isinstance(val, dict):
            v = val.get("value", "")
            if v is None:
                return ""
            return v
        if val is None:
            return ""
        return val

    @staticmethod
    def _is_list_render_type(rt):
        """Return True if render_type is list-like (multi-row)."""
        return rt in ("multivalue", "readonlylist")

    @staticmethod
    def _to_array(value):
        """Coerce a list-type interim value into a Python list.

        maitux.calcenhance stores list/calculatedlist values as a JSON *string*
        (e.g. '["2"]'), and that is what folderitem() hands over, so the value
        has to be parsed before it can be spread over rows.  This mirrors the
        native MultiValue widget, which does the same in its to_array().

        Values can also arrive *nested*.  Whenever a stored value failed to
        parse, the raw JSON text ended up inside an editable input, the browser
        collected that text back as a single element and the next save encoded
        it again -- so a field cleared and saved a few times holds things like
        '["[\\"2\\"]", "[\\"2\\"]"]', one level deeper each round.  Unwrapping
        here breaks that loop and recovers the values already mangled by it.
        """
        if value is None or value == "":
            return []
        if isinstance(value, (list, tuple)):
            return _flatten_encoded(list(value))
        raw = value
        if isinstance(raw, bytes):
            # Python 2: str(u"CJK") raises UnicodeEncodeError, so decode
            # instead of stringifying.
            raw = raw.decode("utf-8", "replace")
        parsed = _decode_scalar(raw)
        if parsed is _UNPARSEABLE:
            # A plain display value such as "24.351": one element.
            return [raw]
        # '"[]"' decodes to the *string* "[]", not to a list: keep peeling.
        depth = 0
        while isinstance(parsed, basestring) and depth < _MAX_UNWRAP_DEPTH:  # noqa: F821
            inner = _decode_scalar(parsed.strip())
            if inner is _UNPARSEABLE:
                return [parsed]
            parsed = inner
            depth += 1
        if not isinstance(parsed, list):
            return [parsed]
        return _flatten_encoded(parsed)

    def _has_calculation(self, item):
        """Check whether the analysis of this item is driven by a Calculation.

        Uses the native (memoized) AnalysesView.get_calculation() so the
        answer matches what the calculation engine itself sees.
        """
        brain = item.get("obj")
        if brain is None:
            return False
        try:
            return bool(self.get_calculation(brain))
        except Exception:
            return False

    @staticmethod
    def _is_editable(item, keyword):
        """Check whether the *permissions* allow editing this field.

        `allow_edit` is filled by the native AnalysesView.folderitem() and
        covers the workflow state, the FieldEditAnalysisResult permission and
        the detection limit rules.

        It is not sufficient on its own for interim fields: the native code
        appends *every* interim keyword to allow_edit and has no notion of
        computed fields.  In the ReactJS listing the read-only-ness of a
        computed interim comes solely from its result_type, so callers must
        combine this with _is_interim_readable_only().  See
        senaite.app.listing TableCell.coffee, get_type().
        """
        return keyword in (item.get("allow_edit") or [])

    @classmethod
    def _is_interim_editable(cls, item, column):
        """Editability of one interim cell: permission AND not computed."""
        if column["render_type"] in ("readonly", "readonlylist"):
            return False
        return cls._is_editable(item, column["keyword"])

    @staticmethod
    def _resolve_sample_id(item):
        """Extract sample / request ID from an analysis item dict.

        `getRequestID` is *not* a key of the item dict: folderitems() only
        fills keys listed in `self.columns`, and there is no such column in
        the worksheet listing.  It *is* a metadata column of the analysis
        catalog though, so it can be read straight off the brain kept in
        item["obj"] -- no object wake-up needed.

        Reference analyses (blanks/controls) have no request, hence the
        fallback to the slot number.
        """
        brain = item.get("obj")
        if brain is not None:
            request_id = getattr(brain, "getRequestID", None)
            if request_id:
                return str(request_id)
        # Reference/blank analyses and empty slots have no sample: group them
        # by their slot position instead.
        pos = item.get("Pos", "")
        if pos:
            return "Slot {}".format(pos)
        return "unknown"

    # ------------------------------------------------------------------
    # Grouping
    # ------------------------------------------------------------------

    def _build_interim_columns(self, items):
        """Discover visible interim fields for the given AS items.

        Returns list of dicts: {keyword, title, render_type}
        Hidden fields are excluded.
        """
        cols = collections.OrderedDict()
        for item in items:
            for ifield in item.get("interimfields", []):
                if self._is_hidden(ifield):
                    continue
                kw = ifield.get("keyword", "")
                if not kw or kw in cols:
                    continue
                render_type = self._get_render_type(ifield)
                cols[kw] = {
                    "keyword": kw,
                    "title": ifield.get("title", kw),
                    "render_type": render_type,
                    # Precomputed so the template does not have to reach for
                    # the view's helpers inside a repeat loop.
                    "is_list": self._is_list_render_type(render_type),
                }
        return list(cols.values())

    @staticmethod
    def _choices_to_list(choices_item):
        """Convert a DisplayList or list-of-dicts to a simple list-of-dicts.

        Handles DisplayList (iterable of (key,value) tuples) and
        list-of-dicts with ResultValue/ResultText keys.
        """
        if choices_item is None:
            return []
        # DisplayList or list of tuples
        if hasattr(choices_item, "items"):
            # DisplayList.items() returns list of (key, value) tuples
            result = []
            for item in choices_item.items():
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    result.append({"ResultValue": item[0], "ResultText": item[1]})
                elif isinstance(item, dict):
                    result.append(item)
            return result
        # list of dicts
        if isinstance(choices_item, (list, tuple)):
            result = []
            for item in choices_item:
                if isinstance(item, dict):
                    result.append(item)
            return result
        return []

    def _expand_sample_rows(self, sample_data, columns):
        """Expand a sample's items into display rows.

        Handles list-type interim fields by expanding them into multiple
        sub-rows. Scalar fields use rowspan in the template.

        :param sample_data: dict with sample_id and items list
        :param columns: list of interim column dicts
        :returns: {
            "display_rows": [list of row dicts],
            "row_count": int (for rowspan),
        }
        """
        items = sample_data["items"]

        # Longest list that actually holds data across this sample's analyses.
        max_len = 0
        for item in items:
            for col in columns:
                if not col["is_list"]:
                    continue
                max_len = max(
                    max_len, len(self._get_list_array(item, col["keyword"])))

        max_rows = max(1, max_len)

        has_editable_list = False
        for col in columns:
            # Only a hand-entered list gets the spare slot: a computed list
            # (calculatedlist) has as many elements as the engine produced.
            if col["render_type"] != "multivalue":
                continue
            for item in items:
                if self._is_interim_editable(item, col):
                    has_editable_list = True
                    break
            if has_editable_list:
                break

        # Mirror the native MultiValue widget, which keeps one empty input at
        # the end of the list so further elements can be appended.  Here list
        # elements are laid out as rows, so the spare slot is a trailing blank
        # row -- but only once the field holds data.  With no data at all the
        # single baseline row already *is* that empty slot, and adding another
        # one renders an analysis nobody has touched yet as two blank rows.
        if max_len > 0 and has_editable_list:
            max_rows += 1

        # Build display rows
        display_rows = []
        for row_idx in range(max_rows):
            row = {
                "_row_idx": row_idx,
                "_is_first": (row_idx == 0),
                "sample_id": sample_data["sample_id"] if row_idx == 0 else "",
                "item": items[0] if items else {},
            }
            # Copy core fields from the first item (only on first row)
            if row_idx == 0 and items:
                it = items[0]
                for key in ("Pos", "Result", "DetectionLimitOperand",
                            "Uncertainty", "Specification", "Method",
                            "Instrument", "state_title", "state_class",
                            "Remarks", "uid"):
                    if key in it:
                        row[key] = it[key]
                # Choices (method/instrument dropdowns)
                if "choices" in it:
                    row["_choices"] = it["choices"]
                # Whether these fields may be edited.  `allow_edit` is the
                # native, authoritative flag: it already folds in the workflow
                # state, the field permissions and the detection limit rules.
                #
                # On top of that, the Result of an analysis driven by a
                # Calculation is derived from its interim fields and is
                # rewritten on every recalculation, so typing into it would
                # only ever be discarded: render it read-only.
                row["result_editable"] = (
                    self._is_editable(it, "Result")
                    and not self._has_calculation(it)
                )
                row["method_editable"] = self._is_editable(it, "Method")
                row["instrument_editable"] = self._is_editable(it, "Instrument")

                # Out-of-range flag.  Mirrors the native
                # _folder_item_out_of_range(), which is already computed
                # unconditionally by the inherited folderitem() -- but that
                # writes an <img> straight into item["after"]["Result"],
                # glued together with an unrelated "Recalculate" ajax link
                # that only works under the ReactJS listing's own click
                # handler.  Recomputing the flag here and rendering our own
                # icon avoids dragging that dead link along.
                #
                # is_out_of_range() returns (out_range, out_shoulders):
                #   out_range=True,  out_shoulders=True  -> hard fail   (exclamation)
                #   out_range=True,  out_shoulders=False -> soft warning (shoulder band)
                #   out_range=False, *                   -> in range    (no icon)
                out_range, out_shoulders = False, True
                brain = it.get("obj")
                if brain is not None:
                    try:
                        out_range, out_shoulders = is_out_of_range(brain)
                    except Exception:
                        out_range, out_shoulders = False, True
                row["result_out_of_range"] = out_range
                row["result_hard_fail"] = out_range and out_shoulders
                row["result_shoulder_warning"] = out_range and not out_shoulders

            # Interim field values per row index.  Each value carries the UID
            # of the analysis that owns it plus its editability, so the
            # template can emit the data-uid/data-keyword pairs the save
            # queue needs without guessing.
            row["interim"] = {}
            row["interim_uid"] = {}
            row["interim_editable"] = {}
            for item in items:
                for col in columns:
                    kw = col["keyword"]
                    if kw in row["interim"]:
                        continue  # already set from another item
                    if col["is_list"]:
                        # One list element per row; the spare trailing row (see
                        # above) stays empty so a new element can be typed in.
                        arr = self._get_list_array(item, kw)
                        row["interim"][kw] = arr[row_idx] if row_idx < len(arr) else ""
                    else:
                        val = self._get_item_field_value(item, kw)
                        row["interim"][kw] = val if row_idx == 0 else ""
                    row["interim_uid"][kw] = item.get("uid", "")
                    row["interim_editable"][kw] = self._is_interim_editable(
                        item, col)

            display_rows.append(row)

        return {
            "display_rows": display_rows,
            "row_count": max_rows,
        }

    def _group_analyses_by_as(self, items):
        """Group flat analysis items by AS Keyword, then by sample.

        Returns list of AS group dicts, each containing:
          - keyword (str)
          - title (str)
          - sort_key (int)
          - interim_columns (list): visible interim column definitions
          - samples (list): list of {
              sample_id (str),
              row_count (int): for rowspan,
              display_rows (list): pre-expanded rows
            }
        """
        if not items:
            return []

        # --- First pass: discover AS keywords ---
        as_info = {}
        for item in items:
            keyword = item.get("Keyword", "")
            if not keyword or keyword in as_info:
                continue
            title = item.get("Service", keyword)
            sort_key = self._get_as_sort_key(item)
            as_info[keyword] = {
                "keyword": keyword,
                "title": title,
                "sort_key": sort_key,
                # For the per-row "Service info" overlay link (audit trail,
                # description, calculation): one Analysis Service per AS
                # group, so it only needs to be resolved once.
                "service_uid": item.get("service_uid", ""),
            }

        if not as_info:
            return []

        # --- Second pass: group items by AS -> sample ---
        sorted_ases = sorted(
            as_info.values(), key=lambda x: (x["sort_key"], x["keyword"])
        )
        grouped = collections.OrderedDict()
        for as_entry in sorted_ases:
            kw = as_entry["keyword"]
            grouped[kw] = {
                "keyword": kw,
                "title": as_entry["title"],
                "sort_key": as_entry["sort_key"],
                "service_uid": as_entry["service_uid"],
                "samples": collections.OrderedDict(),
            }

        for item in items:
            keyword = item.get("Keyword", "")
            if keyword not in grouped:
                continue
            sample_id = self._resolve_sample_id(item)

            od = grouped[keyword]["samples"]
            if sample_id not in od:
                od[sample_id] = {"sample_id": sample_id, "items": []}
            od[sample_id]["items"].append(item)

        # --- Third pass: build columns + expand display rows ---
        result = []
        for kw, grp in grouped.items():
            samples_raw = list(grp["samples"].values())
            grp["samples"] = []

            # Build interim columns from all items in this AS
            all_items = []
            for s in samples_raw:
                all_items.extend(s["items"])
            grp["interim_columns"] = self._build_interim_columns(all_items)

            # Expand each sample
            for s in samples_raw:
                expanded = self._expand_sample_rows(s, grp["interim_columns"])
                expanded["sample_id"] = s["sample_id"]
                # Identifies the rows belonging to one sample within a group,
                # so the client can tell which row is the last of its block.
                # Built here rather than in the template: a `string:` TALES
                # expression is an awkward place to join two values, since
                # Chameleon reads a top-level "|" as its fallback operator and
                # would silently keep only the first half.
                expanded["block_id"] = u"{}::{}".format(kw, s["sample_id"])
                grp["samples"].append(expanded)

            result.append(grp)

        return result

    def get_as_groups(self):
        """Return analyses grouped by AS -> sample.

        Cached per request; lazy-evaluated on first call.
        """
        if self._as_groups is None:
            items = self.folderitems()
            self._as_groups = self._group_analyses_by_as(items)
        return self._as_groups

    def contents_table(self):
        """Render the AS-grouped table HTML.

        This overrides the ListingView.contents_table() (React listing) so
        that when manage_results instantiates us as a layout view, it
        receives our ZPT-rendered AS group panels instead.
        """
        return self.as_grouped_table()

    # ------------------------------------------------------------------
    # Template helpers
    # ------------------------------------------------------------------

    def get_column_count(self, group):
        """Return total column count for an AS group.

        Fixed columns (6) + interim columns.
        Fixed: row-select + Sample + Result + Method + Instrument + State

        The row-select checkbox was missing from the old count; it is a real
        column in the template, so include it rather than keep a total that
        matches nothing on screen.
        """
        fixed = 6
        return fixed + len(group.get("interim_columns", []))

    # Name this view is registered under; the save endpoint is reached by
    # traversing it.  Subclasses set their own.
    view_name = "as_grouped"

    def get_workflow_action_url(self):
        """Return the URL of the native workflow_action endpoint.

        Registered for both IWorksheet and IAnalysisRequest contexts (see
        bika/lims/browser/workflow/configure.zcml), so the same relative
        endpoint serves a worksheet and a sample alike.
        """
        return "{}/workflow_action".format(self.context.absolute_url())

    def get_save_url(self):
        """Return the URL of the native listing save endpoint.

        Built by hand rather than through AjaxListingView.get_api_url(), whose
        result depends on self.__name__.  Traversing this URL instantiates the
        view afresh, so it is independent of how the current page was rendered.
        """
        return "{}/{}/set_fields".format(
            self.context.absolute_url(), self.view_name)

    def get_redirect_url(self):
        """Where workflow_action returns to once it is done."""
        return self.context.absolute_url()

    def get_all_uids(self):
        """Return comma-separated UIDs of all analyses in this worksheet.

        Empty slots are excluded (their UIDs start with "empty-").
        """
        uids = []
        for group in self.get_as_groups():
            for sample in group.get("samples", []):
                for row in sample.get("display_rows", []):
                    uid = row.get("uid", "")
                    if not uid or str(uid).startswith("empty-"):
                        continue
                    if uid in uids:
                        continue
                    uids.append(uid)
        return ",".join(uids)

    def get_service_info_url(self, group, row):
        """URL for the "Service info" overlay (Analysis Service details +
        this analysis instance's audit trail).

        Same relative href the native listing emits before the Service name
        (bika.lims.browser.analyses.view.py, folder_item): the view is
        registered `for="*"` and the click handler that turns it into a modal
        (`a.overlay_panel`) is bound on `document` by senaite.core.site.js --
        a site-wide bundle, not part of the ReactJS listing -- so it works
        exactly the same from our plain server-rendered link.
        """
        uid = row.get("uid", "")
        if not uid or str(uid).startswith("empty-"):
            return ""
        return "analysisservice_info?service_uid={}&analysis_uid={}".format(
            group.get("service_uid", ""), uid)

    def get_method_choices(self, row):
        """Return list of {ResultValue, ResultText} for the Method select."""
        choices = row.get("_choices", {})
        raw = choices.get("Method")
        return self._choices_to_list(raw)

    def get_instrument_choices(self, row):
        """Return list of {ResultValue, ResultText} for Instrument select."""
        choices = row.get("_choices", {})
        raw = choices.get("Instrument")
        return self._choices_to_list(raw)


class AnalysesGroupedView(GroupedRenderingMixin, WorksheetAnalysesView):
    """AS-Grouped layout for a Worksheet.

    Groups the worksheet's analyses by Analysis Service instead of by sample
    slot.  Selected through the stock "Layout" dropdown of manage_results,
    which resolves it with api.get_view("as_grouped").
    """

    view_name = "as_grouped"

    def __call__(self):
        """Redirect direct visits back to manage_results.

        This view only ever renders as a *layout* inside manage_results, which
        calls contents_table() directly.  Rendered standalone it would lack the
        whole manage_results shell (analyst, instrument, remarks, workflow
        buttons), so results could neither be saved nor submitted.

        The subpath check must come first: the AJAX endpoint is reached as
        <worksheet>/as_grouped/set_fields, and publishTraverse() collects
        "set_fields" into traverse_subpath before __call__ runs.  Redirecting
        unconditionally would silently kill the save endpoint.
        """
        if self.traverse_subpath:
            return super(AnalysesGroupedView, self).__call__()
        return self.request.response.redirect(self.get_manage_results_url())

    def get_worksheet_url(self):
        """Return the worksheet's absolute URL for AJAX requests."""
        return self.context.absolute_url()

    def get_manage_results_url(self):
        """Return the manage_results URL (used for redirect after save)."""
        return "{}/manage_results".format(self.context.absolute_url())

    def get_redirect_url(self):
        # Back to the results form, not to the bare worksheet view.
        return self.get_manage_results_url()
