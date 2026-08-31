# -*- coding: utf-8 -*-

import json
import uuid

from plone import api as ploneapi
from zope.component import getUtility
from zope.schema.interfaces import IVocabularyFactory
from zope.schema.vocabulary import SimpleTerm
from zope.schema.vocabulary import SimpleVocabulary

from INNOCARE.arextension.defaults import DEFAULT_HAZARD_CATEGORIES
from INNOCARE.arextension.setuphandlers import translate_with_fallback

from maitux.hazardcategories import _
from maitux.hazardcategories.config import PROJECTNAME

REGISTRY_KEY = "maitux.hazardcategories.categories"
REGISTRY_JSON_KEY = "maitux.hazardcategories.categories.json"
FOLDER_ID = "hazard_categories"

SCOPE_REFERENCE = u"reference"
SCOPE_AR = u"ar"
SCOPE_BOTH = u"both"

USAGE_SCOPE_LABELS = {
    SCOPE_REFERENCE: _(u"scope_reference_only", default=u"Reference only"),
    SCOPE_AR: _(u"scope_ar_only", default=u"AR only (请验单)"),
    SCOPE_BOTH: _(u"scope_both", default=u"Both (Reference + AR)"),
}


def safe_unicode(value):
    if isinstance(value, unicode):
        return value
    if isinstance(value, str):
        return value.decode("utf-8", "replace")
    return unicode(value)


def parse_categories(raw_text):
    categories = []
    for line in safe_unicode(raw_text or u"").splitlines():
        line = line.strip()
        if not line or line.startswith(u"#"):
            continue
        parts = [part.strip() for part in line.split(u"|")]
        while len(parts) < 4:
            parts.append(u"")
        code, name, common, pictogram = parts[:4]
        if not code:
            continue
        categories.append({
            "uid": unicode(uuid.uuid4()),
            "code": code,
            "name": name,
            "common": common,
            "pictogram": pictogram,
            "usage_scope": SCOPE_BOTH,
        })
    return categories


def format_categories_text(categories):
    lines = []
    for cat in categories or []:
        code = safe_unicode(cat.get("code", u"")).strip()
        name = safe_unicode(cat.get("name", u"")).strip()
        common = safe_unicode(cat.get("common", u"")).strip()
        pictogram = safe_unicode(cat.get("pictogram", u"")).strip()
        if not code:
            continue
        lines.append(u"|".join([code, name, common, pictogram]))
    return u"\n".join(lines)


def default_categories_list():
    raw = DEFAULT_CATEGORIES
    if isinstance(raw, list):
        out = []
        for cat in raw:
            if isinstance(cat, dict):
                d = {
                    "uid": unicode(uuid.uuid4()),
                    "code": safe_unicode(cat.get("code", u"")),
                    "name": safe_unicode(cat.get("name", u"")),
                    "common": safe_unicode(cat.get("common", u"")),
                    "pictogram": safe_unicode(cat.get("pictogram", u"")),
                    "usage_scope": safe_unicode(
                        cat.get("usage_scope") or SCOPE_BOTH),
                }
                if d["code"]:
                    out.append(d)
        if out:
            return out
    return parse_categories(DEFAULT_CATEGORIES)


def get_registry_value():
    registry = ploneapi.portal.get_tool("portal_registry")
    if registry is None:
        return DEFAULT_CATEGORIES
    return registry.get(REGISTRY_KEY, DEFAULT_CATEGORIES)


def get_registry_json():
    registry = ploneapi.portal.get_tool("portal_registry")
    if registry is None:
        return default_categories_list()
    try:
        raw = registry.get(REGISTRY_JSON_KEY, None)
    except Exception:
        raw = None
    if raw:
        try:
            data = json.loads(safe_unicode(raw).encode("utf-8"))
            if isinstance(data, list):
                normalized = []
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    d = {
                        "uid": safe_unicode(item.get("uid") or uuid.uuid4()),
                        "code": safe_unicode(item.get("code", u"")).strip(),
                        "name": safe_unicode(item.get("name", u"")).strip(),
                        "common": safe_unicode(item.get("common", u"")).strip(),
                        "pictogram": safe_unicode(
                            item.get("pictogram", u"")).strip(),
                        "usage_scope": safe_unicode(
                            item.get("usage_scope") or SCOPE_BOTH),
                    }
                    if d["code"]:
                        normalized.append(d)
                if normalized:
                    return normalized
        except Exception:
            pass
    text_value = get_registry_value()
    parsed = parse_categories(text_value)
    if not parsed:
        parsed = default_categories_list()
    save_registry_json(parsed)
    return parsed or []


def save_registry_json(categories):
    registry = ploneapi.portal.get_tool("portal_registry")
    if registry is None:
        raise RuntimeError("portal_registry tool not found")
    normalized = []
    for cat in categories or []:
        if not isinstance(cat, dict):
            continue
        d = {
            "uid": safe_unicode(cat.get("uid") or unicode(uuid.uuid4())),
            "code": safe_unicode(cat.get("code", u"")).strip(),
            "name": safe_unicode(cat.get("name", u"")).strip(),
            "common": safe_unicode(cat.get("common", u"")).strip(),
            "pictogram": safe_unicode(cat.get("pictogram", u"")).strip(),
            "usage_scope": safe_unicode(
                cat.get("usage_scope") or SCOPE_BOTH),
        }
        if d["code"]:
            normalized.append(d)
    if REGISTRY_JSON_KEY not in registry.records:
        try:
            from plone.registry.record import Record
            from plone.registry.field import Text as PText
            field = PText(title=u"Hazard categories (JSON)", __name__="value")
            field.interfaceName = (
                "maitux.hazardcategories.interfaces.IHazardCategoriesSettings"
            )
            field.fieldName = "categories_json"
            record = Record(field, u"")
            registry.records[REGISTRY_JSON_KEY] = record
        except Exception:
            pass
    json_text = json.dumps(normalized, ensure_ascii=False, indent=2)
    json_text_u = safe_unicode(json_text)
    try:
        registry[REGISTRY_JSON_KEY] = json_text_u
    except Exception:
        try:
            rec = registry.records.get(REGISTRY_JSON_KEY)
            if rec is not None:
                rec.value = json_text_u
        except Exception:
            pass
    text_lines = []
    for cat in normalized:
        text_lines.append(u"|".join([
            cat["code"], cat["name"], cat["common"], cat["pictogram"]
        ]))
    text_value = u"\n".join(text_lines)
    try:
        registry[REGISTRY_KEY] = text_value
    except Exception:
        pass
    return normalized


def _get_hazard_folder():
    try:
        portal = ploneapi.portal.get()
        if portal is None:
            return None
    except Exception:
        return None
    folder = getattr(portal, FOLDER_ID, None)
    if folder is None:
        try:
            folder = portal[FOLDER_ID]
        except Exception:
            return None
    pt = getattr(folder, "portal_type", None)
    if pt in ("HazardCategories", "Folder"):
        return folder
    return None


def _get_categories_from_folder():
    folder = _get_hazard_folder()
    if folder is None:
        return None
    try:
        ids = list(getattr(folder, "objectIds", lambda: [])())
    except Exception:
        return None
    if not ids:
        return []
    items = []
    for cid in ids:
        try:
            obj = folder[cid]
        except Exception:
            continue
        pt = getattr(obj, "portal_type", None)
        if pt != "HazardCategory":
            continue
        code = safe_unicode(getattr(obj, "code", None) or u"").strip()
        if not code:
            continue
        usage_scope = safe_unicode(
            getattr(obj, "usage_scope", None) or SCOPE_BOTH).strip()
        if usage_scope not in USAGE_SCOPE_LABELS:
            usage_scope = SCOPE_BOTH
        items.append({
            "code": code,
            "name": safe_unicode(getattr(obj, "name", None) or u"").strip(),
            "common": safe_unicode(getattr(obj, "common", None) or u"").strip(),
            "pictogram": safe_unicode(
                getattr(obj, "pictogram", None) or u"").strip(),
            "usage_scope": usage_scope,
        })
    items.sort(key=lambda c: (c["code"].lower(), c["name"].lower()))
    return items


def _get_categories_from_catalog():
    try:
        from bika.lims import api
        from senaite.core.catalog import SETUP_CATALOG
        catalog = api.get_tool(SETUP_CATALOG)
        if catalog is None:
            return None
        brains = catalog(portal_type="HazardCategory", sort_on="sortable_title")
        if not brains:
            return None
        items = []
        for brain in brains:
            try:
                obj = api.get_object(brain)
            except Exception:
                continue
            code = safe_unicode(getattr(obj, "code", None) or u"").strip()
            if not code:
                continue
            usage_scope = safe_unicode(
                getattr(obj, "usage_scope", None) or SCOPE_BOTH).strip()
            if usage_scope not in USAGE_SCOPE_LABELS:
                usage_scope = SCOPE_BOTH
            items.append({
                "code": code,
                "name": safe_unicode(getattr(obj, "name", None) or u"").strip(),
                "common": safe_unicode(getattr(obj, "common", None) or u"").strip(),
                "pictogram": safe_unicode(
                    getattr(obj, "pictogram", None) or u"").strip(),
                "usage_scope": usage_scope,
            })
        return items
    except Exception:
        return None


def get_categories(scope=None):
    cats = _get_categories_from_folder()
    if cats is None:
        cats = _get_categories_from_catalog()
    if not cats:
        registry_cats = get_registry_json()
        if registry_cats:
            out = []
            for cat in registry_cats:
                usage_scope = safe_unicode(
                    cat.get("usage_scope") or SCOPE_BOTH)
                if usage_scope not in USAGE_SCOPE_LABELS:
                    usage_scope = SCOPE_BOTH
                out.append({
                    "code": cat.get("code", u""),
                    "name": cat.get("name", u""),
                    "common": cat.get("common", u""),
                    "pictogram": cat.get("pictogram", u""),
                    "usage_scope": usage_scope,
                })
            cats = out
        else:
            fallback = parse_categories(DEFAULT_CATEGORIES)
            cats = [
                {
                    "code": c.get("code", u""),
                    "name": c.get("name", u""),
                    "common": c.get("common", u""),
                    "pictogram": c.get("pictogram", u""),
                    "usage_scope": safe_unicode(
                        c.get("usage_scope") or SCOPE_BOTH),
                }
                for c in fallback
            ]
    if scope is None or scope == "all":
        return cats
    filtered = []
    for c in cats:
        s = c.get("usage_scope") or SCOPE_BOTH
        if s == SCOPE_BOTH:
            filtered.append(c)
        elif s == SCOPE_REFERENCE and scope in ("ref", "reference", SCOPE_REFERENCE):
            filtered.append(c)
        elif s == SCOPE_AR and scope in ("ar", SCOPE_AR):
            filtered.append(c)
    return filtered


def get_category(code):
    for category in get_categories():
        if category["code"] == code:
            return category
    return None


def format_title(category):
    code = safe_unicode(category.get("code", u""))
    name = safe_unicode(category.get("name", u""))
    common = safe_unicode(category.get("common", u""))
    if common:
        return u"%s: %s (%s)" % (code, name, common)
    return u"%s: %s" % (code, name)


def _runtime_translate(msg, fallback=None):
    # translate_with_fallback defaults to the INNOCARE.arextension domain,
    # which does not contain the scope-label msgids. Resolve the message's
    # own domain (maitux.hazardcategories) so the package catalog is used
    # and the Chinese translations are picked up at runtime.
    domain = getattr(msg, "domain", None) or PROJECTNAME
    return translate_with_fallback(msg, domain=domain)


def get_scope_label(usage_scope):
    s = safe_unicode(usage_scope or SCOPE_BOTH)
    msg = USAGE_SCOPE_LABELS.get(s, USAGE_SCOPE_LABELS[SCOPE_BOTH])
    return _runtime_translate(msg)


class UsageScopeVocabulary(object):
    """Static vocabulary for usage_scope field.
    """

    def __call__(self, context):
        terms = [
            SimpleTerm(
                value=SCOPE_BOTH,
                token=SCOPE_BOTH,
                title=USAGE_SCOPE_LABELS[SCOPE_BOTH],
            ),
            SimpleTerm(
                value=SCOPE_REFERENCE,
                token=SCOPE_REFERENCE,
                title=USAGE_SCOPE_LABELS[SCOPE_REFERENCE],
            ),
            SimpleTerm(
                value=SCOPE_AR,
                token=SCOPE_AR,
                title=USAGE_SCOPE_LABELS[SCOPE_AR],
            ),
        ]
        return SimpleVocabulary(terms)


UsageScopeVocabularyFactory = UsageScopeVocabulary()


class HazardCategoriesForReferenceVocabulary(object):
    """Vocabulary returning only categories scoped for Reference Definition.
    """

    def __call__(self, context):
        terms = [
            SimpleTerm(
                value=category["code"],
                token=category["code"],
                title=format_title(category),
            )
            for category in get_categories(scope="reference")
        ]
        return SimpleVocabulary(terms)


HazardCategoriesForReferenceVocabularyFactory = (
    HazardCategoriesForReferenceVocabulary())


class HazardCategoriesForARVocabulary(object):
    """Vocabulary returning only categories scoped for AR (请验单).
    """

    def __call__(self, context):
        terms = [
            SimpleTerm(
                value=category["code"],
                token=category["code"],
                title=format_title(category),
            )
            for category in get_categories(scope="ar")
        ]
        return SimpleVocabulary(terms)


HazardCategoriesForARVocabularyFactory = HazardCategoriesForARVocabulary()


class EditableHazardCategoriesVocabulary(object):
    """Vocabulary returning all Hazard categories (Both + Reference + AR).
    """

    def __call__(self, context):
        terms = [
            SimpleTerm(
                value=category["code"],
                token=category["code"],
                title=format_title(category),
            )
            for category in get_categories()
        ]
        return SimpleVocabulary(terms)


EditableHazardCategoriesVocabularyFactory = EditableHazardCategoriesVocabulary()
