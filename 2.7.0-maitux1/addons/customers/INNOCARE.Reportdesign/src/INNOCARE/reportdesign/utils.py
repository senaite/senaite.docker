# -*- coding: utf-8 -*-
"""INNOCARE.Reportdesign utilities

NOTE:
This package runs in the MaituxLIMS environment (SENAITE 2.x / Plone 5.2 / Py2.7).
This module is designed to be callable from restricted page templates via:

    modules['INNOCARE.reportdesign.utils']
"""

from __future__ import absolute_import

from bika.lims import api


def _as_unicode(value):
    """Best-effort unicode conversion for template rendering."""
    if value is None:
        return u""
    try:
        # Py2
        if isinstance(value, unicode):
            return value
    except NameError:
        pass
    try:
        return api.safe_unicode(value)
    except Exception:
        try:
            return unicode(value)
        except Exception:
            return u""


def _format_date(value):
    if not value:
        return u""
    # DateTime (Zope) provides strftime; python datetime too
    try:
        return _as_unicode(value.strftime("%Y-%m-%d"))
    except Exception:
        return _as_unicode(value)


def _title(obj):
    if not obj:
        return u""
    try:
        if hasattr(obj, "Title") and callable(obj.Title):
            return _as_unicode(obj.Title())
    except Exception:
        pass
    return _as_unicode(obj)


def _resolve_uid(value):
    """Resolve UID->object if value looks like a UID."""
    try:
        if api.is_uid(value):
            return api.get_object_by_uid(value)
    except Exception:
        pass
    return value


def _get_reference_field_title(value):
    """ReferenceWidget/UIDReferenceField value may be object or UID."""
    obj = _resolve_uid(value)
    return _title(obj)


def _get_ar_analyses(ar):
    """Return analysis objects for an AR, tolerant to API differences."""
    if ar is None or not hasattr(ar, "getAnalyses"):
        return []

    try:
        analyses = ar.getAnalyses(full_objects=True)
    except TypeError:
        analyses = ar.getAnalyses()
    except Exception:
        analyses = ar.getAnalyses()

    if not analyses:
        return []

    # Sometimes it returns a list of UIDs
    try:
        first = analyses[0]
        if isinstance(first, basestring) and api.is_uid(first):
            objs = []
            for uid in analyses:
                try:
                    if api.is_uid(uid):
                        obj = api.get_object_by_uid(uid)
                        if obj is not None:
                            objs.append(obj)
                except Exception:
                    continue
            analyses = objs
    except Exception:
        pass

    return list(analyses)


def _first(*values):
    for v in values:
        if v not in (None, u"", ""):
            return v
    return u""


def _analysis_method_title(analysis):
    """Try to infer method title for a given analysis."""
    if analysis is None:
        return u""
    # Direct method on analysis
    try:
        m = getattr(analysis, "getMethod", None)
        if callable(m):
            mo = m()
            if mo:
                return _title(mo)
    except Exception:
        pass
    # Method on service
    try:
        svc = getattr(analysis, "getService", None)
        if callable(svc):
            svc = svc()
        if svc and hasattr(svc, "getMethod") and callable(svc.getMethod):
            mo = svc.getMethod()
            if mo:
                return _title(mo)
    except Exception:
        pass
    return u""


def _analysis_accept_criteria(analysis):
    """Try to infer accept criteria/specs for a given analysis."""
    if analysis is None:
        return u""
    for name in (
        "getFormattedSpecs",
        "getFormattedSpecification",
        "getSpecification",
        "getResultRange",
        "getResultsRange",
        "getMinMax",
    ):
        try:
            fn = getattr(analysis, name, None)
            if callable(fn):
                v = fn()
                if v not in (None, u"", ""):
                    return _as_unicode(v)
        except Exception:
            continue
    return u""


def _analysis_result(analysis):
    """Try to infer formatted result for a given analysis."""
    if analysis is None:
        return u""
    for name in (
        "getFormattedResult",
        "getResult",
        "getRawResult",
    ):
        try:
            fn = getattr(analysis, name, None)
            if callable(fn):
                v = fn()
                if v not in (None, u"", ""):
                    return _as_unicode(v)
        except Exception:
            continue
    return u""


def get_coa_data(ar):
    """Build a data dict for COA template rendering.

    This function purposely does NOT enforce hard dependencies on a specific
    print view. It only needs an AnalysisRequest-like object.
    """
    if ar is None:
        return {"meta": {}, "rows": []}

    # --- Meta (header table) ---
    getv = lambda name, default=u"": _as_unicode(getattr(ar, name, lambda: default)())

    meta = {
        # Identifiers
        # NOTE: User decision (2026-08-28): Report ID is manually filled when issuing the report.
        # Keep it empty by default (do NOT fallback to AR id).
        "report_id": _first(getv("getReportID"), getv("getCoAID"), u""),
        "project_id": _get_reference_field_title(_first(getv("getProjectNo"), getv("ProjectNo"))),
        "coa_version": _first(getv("getCoAVersion"), u""),
        # Material
        "compound_id": _first(getv("getMaterialCode"), u""),
        "material_name": _first(getv("getMaterialName"), u""),
        "strength": _first(getv("getStrength"), u""),
        "batch_no": _first(getv("getClientReference"), u""),
        "batch_size": u" ".join([v for v in [getv("getQuantity"), getv("getUnit")] if v]).strip(),
        # Dates
        "manufacture_date": _format_date(_first(getv("getManufactureDate"), u"")),
        "test_date": _format_date(_first(getv("getTestDate"), getv("getDateSampled"), getv("getDateReceived"), u"")),
        "retest_date": _format_date(_first(getv("getRetestDate"), u"")),
        # Misc
        # NOTE: User decision (2026-08-28): Manufacturer is manually filled when issuing the report.
        "manufacturer": u"",
        "storage_conditions": _get_reference_field_title(_first(getv("getStorageConditions"), u"")),
        "comment": _first(getv("getSafetyPrecautions"), getv("getRemarks"), u""),
    }

    # --- Rows (analysis table) ---
    rows = []
    for an in _get_ar_analyses(ar):
        rows.append(
            {
                "testing_item": _title(an),
                "method": _analysis_method_title(an),
                "accept_criteria": _analysis_accept_criteria(an),
                "result": _analysis_result(an),
            }
        )

    return {"meta": meta, "rows": rows}
