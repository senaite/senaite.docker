# -*- coding: utf-8 -*-
import logging
log = logging.getLogger("INNOCARE.arextension")
log.info("LOADING AREXTENSION MODULE")
from bika.lims.interfaces import IAnalysisRequest
from zope.component import adapts
from zope.interface import implements
from zope.interface import classImplements
from archetypes.schemaextender.interfaces import IBrowserLayerAwareExtender
from archetypes.schemaextender.field import ExtensionField
from archetypes.schemaextender.interfaces import ISchemaExtender
from archetypes.schemaextender.interfaces import ISchemaModifier
from Products.Archetypes.public import StringField
from Products.Archetypes.public import DateTimeField
from Products.Archetypes.public import TextField
from Products.Archetypes.public import LinesField
from Products.Archetypes.public import StringWidget
from Products.Archetypes.public import CalendarWidget
from Products.Archetypes.public import TextAreaWidget
from Products.Archetypes.public import SelectionWidget
from Products.Archetypes.public import MultiSelectionWidget
from Products.Archetypes.public import DisplayList
from bika.lims.browser.widgets import DateTimeWidget
from bika.lims.browser.fields import UIDReferenceField
from senaite.core.browser.widgets.referencewidget import ReferenceWidget
from senaite.core.catalog import SETUP_CATALOG
from zope.publisher.interfaces.browser import IDefaultBrowserLayer

from INNOCARE.arextension import _

from Products.CMFCore.utils import getToolByName
from zope.globalrequest import getRequest
from zope.i18n import translate as _zt

SAFE_SCOPE_AR = (u"ar", u"AR", u"ar_only", u"both", u"Both", u"请验单", u"全部")


def _query_setup_catalog(context, portal_type=None,
                         setup_catalog_name="senaite_catalog_setup",
                         extra_queries=None, folder_id=None,
                         setup_only=False):
    portal = None
    if context is not None:
        portal = getattr(context, "aq_parent", None)
        while portal is not None and not hasattr(portal, "portal_catalog"):
            portal = getattr(portal, "aq_parent", None)
    if portal is None:
        try:
            from zope.component.hooks import getSite as _getSite
            s = _getSite()
            if hasattr(s, "portal_catalog"):
                portal = s
        except Exception:
            portal = None
    if portal is None:
        try:
            parents = getattr(getRequest(), "PARENTS", None) or []
            for p in parents:
                if hasattr(p, "portal_catalog"):
                    portal = p
                    break
        except Exception:
            portal = None
    if portal is None:
        return []
    brains = []
    if folder_id is not None:
        folder = getattr(portal, folder_id, None)
        if folder is not None and hasattr(folder, "items"):
            results = []
            for (k, obj) in folder.items():
                if portal_type is None or getattr(obj, "portal_type", "") == portal_type:
                    results.append(obj)
            return results
    if extra_queries is None:
        extra_queries = {}
    if portal_type is not None:
        extra_queries["portal_type"] = portal_type
    try:
        sc = getToolByName(portal, setup_catalog_name)
        try:
            brains = list(sc(**extra_queries))
        except Exception:
            brains = []
    except Exception:
        brains = []
    if not brains and not setup_only:
        try:
            pc = getToolByName(portal, "portal_catalog")
            brains = list(pc(**extra_queries))
        except Exception:
            brains = []
    objs = []
    for b in brains:
        try:
            objs.append(b.getObject())
        except Exception:
            continue
    return objs


def _safe_uid(obj):
    try:
        uid = getattr(obj, "UID", None)
        if callable(uid):
            return obj.UID()
        return uid or obj.getId() or u""
    except Exception:
        return u""


def _safe_title(obj):
    title = u""
    try:
        title = getattr(obj, "Title", None)
        if callable(title):
            title = title()
    except Exception:
        title = u""
    if not title:
        title = getattr(obj, "title", None) or u""
    return unicode(title or u"").strip()


from Products.Archetypes.public import DisplayList


class _CallableVocab(list):
    __allow_access_to_unprotected_subobjects__ = 1

    def __init__(self, factory):
        list.__init__(self)
        self._factory = factory
        self._cached_dl = None
        self._populated = False

    def _populate(self, context=None):
        if self._populated:
            return
        try:
            res = self._factory(context)
            if isinstance(res, DisplayList):
                dl = res
                tuples = [(k, dl.getValue(k)) for k in dl.keys()]
            else:
                tuples = list(res or [])
                dl = DisplayList(tuples)
            list.__init__(self, tuples)
            self._cached_dl = dl
        except Exception as exc:
            import logging as _lg
            _lg.getLogger("INNOCARE.arextension").exception(
                "_CallableVocab populate %s failed: %s",
                getattr(self._factory, "__name__", repr(self._factory)),
                exc,
            )
            list.__init__(self, [])
            self._cached_dl = DisplayList([])
        self._populated = True

    def __getitem__(self, item):
        self._populate(None)
        return list.__getitem__(self, item)

    def __getslice__(self, i, j):
        self._populate(None)
        return list.__getslice__(self, i, j)

    def __len__(self):
        self._populate(None)
        return list.__len__(self)

    def __iter__(self):
        self._populate(None)
        return list.__iter__(self)

    def __contains__(self, item):
        self._populate(None)
        return list.__contains__(self, item)

    def __nonzero__(self):
        self._populate(None)
        return list.__len__(self) > 0

    __bool__ = __nonzero__

    def items(self):
        self._populate(None)
        return tuple(list.__iter__(self))

    def keys(self):
        self._populate(None)
        return [kv[0] for kv in list.__iter__(self)]

    def values(self):
        self._populate(None)
        return [kv[1] for kv in list.__iter__(self)]

    def __call__(self, context=None):
        self._populate(context)
        return self._cached_dl


def _build_projects_items(context=None):
    objs = _query_setup_catalog(context, portal_type="Project",
                                folder_id="projects")
    items = []
    seen = set()
    for o in objs:
        key = unicode(o.getId() or u"")
        if not key or key in seen:
            continue
        seen.add(key)
        title = _safe_title(o) or key
        items.append((key, title))
    items.sort(key=lambda kv: kv[1].lower())
    return items


def ProjectsVocabulary(context=None):
    return DisplayList(_build_projects_items(context))


def _build_sample_matrices_items(context=None):
    objs = _query_setup_catalog(context, portal_type="SampleMatrix")
    items = []
    seen = set()
    for o in objs:
        key = _safe_uid(o)
        if not key or key in seen:
            continue
        seen.add(key)
        title = _safe_title(o) or unicode(getattr(o, "title", u"") or o.getId())
        items.append((key, title))
    items.sort(key=lambda kv: kv[1].lower())
    return items


def SampleMatricesVocabulary(context=None):
    return DisplayList(_build_sample_matrices_items(context))


def _build_sample_preservations_items(context=None):
    objs = _query_setup_catalog(context, portal_type="SamplePreservation")
    if not objs:
        objs = _query_setup_catalog(context, portal_type="StorageCondition")
    if not objs:
        objs = _query_setup_catalog(context, portal_type="SampleCondition")
    items = []
    seen = set()
    for o in objs:
        key = _safe_uid(o)
        if not key or key in seen:
            continue
        seen.add(key)
        title = _safe_title(o) or unicode(getattr(o, "title", u"") or o.getId())
        items.append((key, title))
    items.sort(key=lambda kv: kv[1].lower())
    return items


def SamplePreservationsVocabulary(context=None):
    return DisplayList(_build_sample_preservations_items(context))


def _build_sample_properties_items(context=None):
    objs = _query_setup_catalog(context, portal_type="HazardCategory",
                                folder_id="hazard_categories")
    items = []
    seen = set()
    request = None
    lang = None
    try:
        request = getRequest()
        if request is not None:
            lang = (getattr(request, "locale", None)
                    and request.locale.getLocaleID()) or None
            if not lang:
                lang = (request.get("LANGUAGE") or
                        request.cookies.get("I18N_LANGUAGE") or u"")
    except Exception:
        lang = None
    zh = bool(lang and (unicode(lang).lower().startswith("zh") or u"zh" in unicode(lang).lower()))
    for o in objs:
        code = unicode(getattr(o, "code", None) or u"").strip()
        usage_scope = unicode(getattr(o, "usage_scope", None) or u"both").strip().lower()
        if usage_scope not in (u"both", u"ar", u"ar_only"):
            continue
        key = code or _safe_uid(o)
        if not key or key in seen:
            continue
        seen.add(key)
        common = unicode(getattr(o, "common", None) or u"").strip()
        name = unicode(getattr(o, "name", None) or u"").strip()
        if zh:
            label = (u"%s %s" % (code, common)).strip() if common else code or name
        else:
            label = (u"%s %s" % (code, name)).strip() if name else code or common
        items.append((key, label))
    items.sort(key=lambda kv: kv[1].lower())
    return items


def SamplePropertiesVocabulary(context=None):
    return DisplayList(_build_sample_properties_items(context))


ProjectsVocabularyFactory = _CallableVocab(_build_projects_items)
SampleMatricesVocabularyFactory = _CallableVocab(_build_sample_matrices_items)
SamplePreservationsVocabularyFactory = _CallableVocab(_build_sample_preservations_items)
SamplePropertiesVocabularyFactory = _CallableVocab(_build_sample_properties_items)


class IARExtensionLayer(IDefaultBrowserLayer):
    pass

class StringExtensionField(ExtensionField, StringField):
    pass

class DateTimeExtensionField(ExtensionField, DateTimeField):
    pass

class TextExtensionField(ExtensionField, TextField):
    pass

class LinesExtensionField(ExtensionField, LinesField):
    pass

class UIDReferenceExtensionField(ExtensionField, UIDReferenceField):
    pass

class ARSchemaExtender(object):
    adapts(IAnalysisRequest)
    implements(ISchemaExtender, IBrowserLayerAwareExtender)
    layer = IARExtensionLayer

    fields = [
        UIDReferenceExtensionField(
            "ProjectNo",
            required=False,
            searchable=True,
            schemata="default",
            allowed_types=("Project",),
            multiValued=False,
            widget=ReferenceWidget(
                label=_(u"Project", default=u"Project"),
                # 关联项目：按项目 ID 选择
                # （说明写入注释，不在界面上显示括号备注）
                description=u"",
                catalog="portal_catalog",
                query={
                    "portal_type": "Project",
                    "sort_on": "sortable_title",
                    "sort_order": "ascending",
                },
                visible={'edit': 'visible', 'view': 'visible', 'add': 'edit'},
                render_own_label=True,
            ),
        ),
        StringExtensionField(
            "MaterialCode",
            required=False,
            searchable=True,
            schemata="default",
            widget=StringWidget(
                label=_(u"Material Code"),
                description=_(u"Material Code"),
                visible={'edit': 'visible', 'view': 'visible', 'add': 'edit'},
                render_own_label=True,
            ),
        ),
        StringExtensionField(
            "MaterialName",
            required=True,
            searchable=True,
            schemata="default",
            widget=StringWidget(
                label=_(u"Material Name"),
                description=_(u"Material Name"),
                visible={'edit': 'visible', 'view': 'visible', 'add': 'edit'},
                render_own_label=True,
            ),
        ),
        StringExtensionField(
            "Strength",
            required=False,
            searchable=True,
            schemata="default",
            widget=StringWidget(
                label=_(u"Strength"),
                description=_(u"Strength / Specification"),
                visible={'edit': 'visible', 'view': 'visible', 'add': 'edit'},
                render_own_label=True,
            ),
        ),
        DateTimeExtensionField(
            "ManufactureDate",
            required=False,
            schemata="default",
            widget=DateTimeWidget(
                label=_(u"Manufacture Date"),
                description=_(u"Manufacture Date"),
                show_time=False,
                visible={'edit': 'visible', 'view': 'visible', 'add': 'edit'},
                render_own_label=True,
            ),
        ),
        StringExtensionField(
            "Quantity",
            required=False,
            searchable=True,
            schemata="default",
            widget=StringWidget(
                label=_(u"Quantity"),
                description=_(u"Quantity"),
                visible={'edit': 'visible', 'view': 'visible', 'add': 'edit'},
                render_own_label=True,
            ),
        ),
        StringExtensionField(
            "Unit",
            required=False,
            searchable=True,
            schemata="default",
            widget=StringWidget(
                label=_(u"Unit"),
                description=_(u"Unit"),
                visible={'edit': 'visible', 'view': 'visible', 'add': 'edit'},
                render_own_label=True,
            ),
        ),
        UIDReferenceExtensionField(
            "SampleStatus",
            required=False,
            searchable=True,
            schemata="default",
            allowed_types=("SampleMatrix",),
            multiValued=False,
            widget=ReferenceWidget(
                label=_(u"Sample Status", default=u"Sample Status"),
                # 样品基体：从 SampleMatrices 维护列表选择
                # （说明写入注释，不在界面上显示括号备注）
                description=u"",
                catalog=SETUP_CATALOG,
                query={
                    "portal_type": "SampleMatrix",
                    "sort_on": "sortable_title",
                    "sort_order": "ascending",
                },
                visible={'edit': 'visible', 'view': 'visible', 'add': 'edit'},
                render_own_label=True,
            ),
        ),
        UIDReferenceExtensionField(
            "StorageConditions",
            required=False,
            searchable=True,
            schemata="default",
            allowed_types=("SamplePreservation", "StorageCondition", "SampleCondition"),
            multiValued=False,
            widget=ReferenceWidget(
                label=_(u"Storage Conditions", default=u"Storage Conditions"),
                # 样品基体储存条件：从 SamplePreservations 维护列表选择
                # （说明写入注释，不在界面上显示括号备注）
                description=u"",
                catalog=SETUP_CATALOG,
                query={
                    "portal_type": (
                        "SamplePreservation",
                        "StorageCondition",
                        "SampleCondition",
                    ),
                    "sort_on": "sortable_title",
                    "sort_order": "ascending",
                },
                visible={'edit': 'visible', 'view': 'visible', 'add': 'edit'},
                render_own_label=True,
            ),
        ),
        UIDReferenceExtensionField(
            "SampleProperties",
            required=False,
            searchable=True,
            schemata="default",
            allowed_types=("HazardCategory",),
            multiValued=1,
            # 样品性质：多选，仅包含 both + AR only 范围
            # （说明写入注释，不在界面上显示括号备注）
            widget=ReferenceWidget(
                label=_(u"Sample Properties", default=u"Sample Properties"),
                description=u"",
                catalog=SETUP_CATALOG,
                query={
                    "portal_type": "HazardCategory",
                    "usage_scope": [u"both", u"ar", u"ar_only"],
                    "sort_on": "sortable_title",
                    "sort_order": "ascending",
                },
                visible={'edit': 'visible', 'view': 'visible', 'add': 'edit'},
                render_own_label=True,
            ),
        ),
        StringExtensionField(
            "SampleRetainer",
            required=False,
            searchable=True,
            schemata="default",
            widget=StringWidget(
                label=_(u"Sample Retainer"),
                description=_(u"Sample Retainer"),
                visible={'edit': 'visible', 'view': 'visible', 'add': 'edit'},
                render_own_label=True,
            ),
        ),
        DateTimeExtensionField(
            "RetentionTime",
            required=False,
            schemata="default",
            widget=DateTimeWidget(
                label=_(u"Retention Time"),
                description=_(u"Retention Time"),
                show_time=False,
                visible={'edit': 'visible', 'view': 'visible', 'add': 'edit'},
                render_own_label=True,
            ),
        ),
        StringExtensionField(
            "SampleRecovery",
            required=False,
            searchable=True,
            vocabulary=DisplayList([
                ("yes", u"是"),
                ("no", u"否"),
            ]),
            schemata="default",
            widget=SelectionWidget(
                format='select',
                label=_(u"Sample Recovery"),
                description=_(u"Sample Recovery Description"),
                visible={'edit': 'visible', 'view': 'visible', 'add': 'edit'},
                render_own_label=True,
            ),
        ),
        TextExtensionField(
            "SafetyPrecautions",
            required=False,
            searchable=True,
            schemata="default",
            widget=TextAreaWidget(
                label=_(u"Safety Precautions"),
                description=_(u"Safety Precautions or Comments"),
                visible={'edit': 'visible', 'view': 'visible', 'add': 'edit'},
                render_own_label=True,
            ),
        ),
    ]

    def __init__(self, context):
        self.context = context

    def getFields(self):
        return self.fields

class ARSchemaModifier(object):
    adapts(IAnalysisRequest)
    implements(ISchemaModifier, IBrowserLayerAwareExtender)
    layer = IARExtensionLayer

    def __init__(self, context):
        self.context = context

    def fiddle(self, schema):
        # 不再硬编码隐藏任何原生字段。字段显隐交由 SENAITE 原生的
        # Manage Sample Form Fields 手工配置（存 ZODB，跨容器重启持久化）。

        if "ClientReference" in schema:
            schema["ClientReference"].widget.label = _(u"Batch No")
            schema["ClientReference"].widget.description = _(u"Batch No")
        if "Contact" in schema:
            schema["Contact"].widget.label = _(u"Applicant")
            schema["Contact"].widget.description = _(u"Applicant / Contact")
        if "StorageLocation" in schema:
            schema["StorageLocation"].widget.label = _(u"Reserved Position")
            schema["StorageLocation"].widget.description = _(u"Reserved Position")
