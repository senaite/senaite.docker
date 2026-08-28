# -*- coding: utf-8 -*-
from bika.lims.interfaces import IDeactivable
from plone.indexer import indexer
from senaite.core.catalog import SETUP_CATALOG
from senaite.core.content.base import Container
from senaite.core.interfaces import ISetupCatalog
from zope.interface import implementer

from maitux.hazardcategories.interfaces import IHazardCategory
from maitux.hazardcategories.interfaces import IHazardCategorySchema


@implementer(IHazardCategory, IHazardCategorySchema, IDeactivable)
class HazardCategory(Container):
    _catalogs = [SETUP_CATALOG]

    def get_catalogs(self):
        return list(self._catalogs or [])

    def Title(self):
        code = getattr(self, "code", None) or u""
        name = getattr(self, "name", None) or u""
        common = getattr(self, "common", None) or u""
        code = safe_unicode(code).strip()
        name = safe_unicode(name).strip()
        common = safe_unicode(common).strip()
        lang = None
        try:
            from zope.globalrequest import getRequest
            req = getRequest()
            if req is not None:
                lang = (getattr(req, "locale", None) and
                        req.locale.getLocaleID()) or None
                if not lang:
                    lang = req.get("LANGUAGE") or req.cookies.get("I18N_LANGUAGE")
        except Exception:
            lang = None
        if lang and str(lang).lower().startswith("zh"):
            raw_label = common or name
        else:
            raw_label = name or common
        def _sanitize(t):
            if not t:
                return u""
            for ch in (u"/", u"\\", u"(", u")", u"[", u"]", u"{", u"}",
                       u"|", u"!", u"?", u"#", u"<", u">", u"*", u":", u"\"",
                       u"'", u"~", u"`", u"^", u"%", u"$", u"@", u"&", u"-"):
                t = t.replace(ch, u" ")
            while u"  " in t:
                t = t.replace(u"  ", u" ")
            return t.strip()
        label = _sanitize(raw_label)
        if code and label:
            return u"%s %s" % (code, label)
        return _sanitize(code) or label or u""

    def Description(self):
        parts = []
        common = getattr(self, "common", None)
        pict = getattr(self, "pictogram", None)
        if common:
            parts.append(safe_unicode(common).strip())
        if pict:
            parts.append(safe_unicode(pict).strip())
        return u" | ".join(parts)


def safe_unicode(value):
    if value is None:
        return u""
    if isinstance(value, unicode):
        return value
    if isinstance(value, str):
        try:
            return value.decode("utf-8")
        except Exception:
            try:
                return value.decode("latin-1", errors="replace")
            except Exception:
                return u""
    return unicode(value)


@indexer(IHazardCategory, ISetupCatalog)
def usage_scope(instance):
    """Indexer for the ``usage_scope`` KeywordIndex in senaite_catalog_setup.

    The AR ``SampleProperties`` ReferenceWidget queries this index with
    ``usage_scope=[both, ar, ar_only]``. Without this indexer the KeywordIndex
    stays empty and the widget returns no candidates.
    """
    value = getattr(instance, "usage_scope", None)
    if not value:
        return u"both"
    return value


@indexer(IHazardCategory, ISetupCatalog)
def allowed_roles_and_users(instance):
    """Indexer for the ``allowedRolesAndUsers`` KeywordIndex.

    Dexterity content does not provide an ``allowedRolesAndUsers`` method
    (Archetypes mixins do), so without this indexer the CMF security filter
    of ``senaite_catalog_setup`` matches no role and the AR
    ``SampleProperties`` ReferenceWidget gets no candidates.
    """
    allowed = set()
    for permission in ("Access contents information", "View"):
        try:
            for entry in instance.rolesOfPermission(permission):
                name = entry.get("name")
                if name:
                    allowed.add(name)
        except Exception:
            continue
    if "Anonymous" in allowed:
        return ["Anonymous"]
    if "Authenticated" in allowed:
        return ["Authenticated"]
    try:
        for userid, roles in instance.get_local_roles():
            if allowed.intersection(roles):
                allowed.add("user:" + userid)
    except Exception:
        pass
    allowed.discard("Owner")
    if not allowed:
        # Fallback: visible to all authenticated users, like other setup data
        return ["Authenticated"]
    return list(allowed)
