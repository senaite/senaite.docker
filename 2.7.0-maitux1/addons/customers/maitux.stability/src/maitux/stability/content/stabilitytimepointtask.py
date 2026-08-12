# -*- coding: utf-8 -*-
from bika.lims import senaiteMessageFactory as _
from plone.autoform import directives
from plone.supermodel import model
from senaite.core.catalog import SETUP_CATALOG
from senaite.core.catalog import SENAITE_CATALOG
from senaite.core.config.widgets import get_default_columns
from senaite.core.content.base import Item
from senaite.core.schema import DatetimeField
from senaite.core.schema import UIDReferenceField
from senaite.core.z3cform.widgets.uidreference import UIDReferenceWidgetFactory
from z3c.form.interfaces import IAddForm
from zope import schema
from zope.interface import Invalid
from zope.interface import implementer
from zope.interface import invariant
from zope.schema.vocabulary import SimpleTerm
from zope.schema.vocabulary import SimpleVocabulary

from maitux.stability.interfaces import IStabilityTimepointTask


ORIENTATION_VOCABULARY = SimpleVocabulary((
    SimpleTerm(value=u"upright", token="upright", title=_(u"Upright")),
    SimpleTerm(value=u"inverted", token="inverted", title=_(u"Inverted")),
    SimpleTerm(value=u"horizontal", token="horizontal", title=_(u"Horizontal")),
))

DETAIL_STATUS_VOCABULARY = SimpleVocabulary((
    SimpleTerm(value=u"pending_placement", token="pending_placement", title=_(u"Pending Placement")),
    SimpleTerm(value=u"active", token="active", title=_(u"Active")),
    SimpleTerm(value=u"completed", token="completed", title=_(u"Completed")),
))

MONTHS_VOCABULARY = SimpleVocabulary(tuple([
    SimpleTerm(value=month, token=str(month), title=u"%s" % month)
    for month in range(1, 13)
]))


class IStabilityTimepointTaskSchema(model.Schema):
    sequence = schema.Int(
        title=_(u"Sequence"),
        required=False,
        default=0,
        min=0,
    )
    directives.mode(sequence="hidden")
    directives.mode(IAddForm, sequence="hidden")

    directives.widget(
        "packaging_specification",
        UIDReferenceWidgetFactory,
        catalog=SETUP_CATALOG,
        query={
            "portal_type": "PackagingSpecification",
            "is_active": True,
            "sort_on": "sortable_title",
            "sort_order": "ascending",
        },
        display_template="<a href='${url}'>${Title}</a>",
        columns=get_default_columns,
    )
    packaging_specification = UIDReferenceField(
        title=_(u"Packaging Specification"),
        allowed_types=("PackagingSpecification",),
        multi_valued=False,
        required=False,
    )

    directives.widget(
        "storage_condition",
        UIDReferenceWidgetFactory,
        catalog=SETUP_CATALOG,
        query={
            "portal_type": "StorageCondition",
            "is_active": True,
            "sort_on": "sortable_title",
            "sort_order": "ascending",
        },
        display_template="<a href='${url}'>${Title}</a>",
        columns=get_default_columns,
    )
    storage_condition = UIDReferenceField(
        title=_(u"Storage Condition"),
        allowed_types=("StorageCondition",),
        multi_valued=False,
        required=False,
    )

    orientation = schema.Choice(
        title=_(u"Orientation"),
        vocabulary=ORIENTATION_VOCABULARY,
        required=False,
        default=u"upright",
    )

    timepoint_days = schema.Choice(
        title=_(u"Timepoint (Months)"),
        required=True,
        vocabulary=MONTHS_VOCABULARY,
    )

    window_days = schema.Int(
        title=_(u"Window (Days)"),
        required=False,
        default=0,
        min=0,
    )

    directives.widget(
        "analysis_specification",
        UIDReferenceWidgetFactory,
        catalog=SETUP_CATALOG,
        query={
            "portal_type": "AnalysisSpec",
            "is_active": True,
            "sort_on": "sortable_title",
            "sort_order": "ascending",
        },
        display_template="<a href='${url}'>${Title}</a>",
        columns=get_default_columns,
    )
    analysis_specification = UIDReferenceField(
        title=_(u"Analysis Specification"),
        allowed_types=("AnalysisSpec",),
        multi_valued=False,
        required=False,
    )

    directives.widget(
        "analysis_profile",
        UIDReferenceWidgetFactory,
        catalog=SETUP_CATALOG,
        query={
            "portal_type": "AnalysisProfile",
            "is_active": True,
            "sort_on": "sortable_title",
            "sort_order": "ascending",
        },
        display_template="<a href='${url}'>${Title}</a>",
        columns=get_default_columns,
    )
    analysis_profile = UIDReferenceField(
        title=_(u"Analysis Profile"),
        allowed_types=("AnalysisProfile",),
        multi_valued=False,
        required=False,
    )

    inspection_quantity = schema.Int(
        title=_(u"Inspection Quantity"),
        required=False,
        default=0,
        min=0,
    )

    directives.widget(
        "batch",
        UIDReferenceWidgetFactory,
        catalog=SENAITE_CATALOG,
        query={
            "portal_type": "Batch",
            "is_active": True,
            "sort_on": "created",
            "sort_order": "descending",
        },
        display_template="<a href='${url}'>${Title}</a>",
        columns=get_default_columns,
    )
    batch = UIDReferenceField(
        title=_(u"Batch"),
        allowed_types=("Batch",),
        multi_valued=False,
        required=False,
    )

    detail_status = schema.Choice(
        title=_(u"Status"),
        vocabulary=DETAIL_STATUS_VOCABULARY,
        required=True,
        default=u"pending_placement",
    )

    directives.widget(
        "stock_batch",
        UIDReferenceWidgetFactory,
        catalog="portal_catalog",
        query={
            "portal_type": "StockBatch",
            "review_state": "active",
            "sort_on": "sortable_title",
            "sort_order": "ascending",
        },
        display_template="<a href='${url}'>${Title}</a>",
        columns=get_default_columns,
    )
    stock_batch = UIDReferenceField(
        title=_(u"Stock Batch"),
        allowed_types=("StockBatch",),
        multi_valued=False,
        required=False,
    )

    directives.mode(target_date="display")
    directives.mode(IAddForm, target_date="hidden")
    target_date = DatetimeField(
        title=_(u"Target Date"),
        required=False,
        readonly=True,
    )

    directives.mode(window_start="display")
    directives.mode(IAddForm, window_start="hidden")
    window_start = DatetimeField(
        title=_(u"Window Start"),
        required=False,
        readonly=True,
    )

    directives.mode(window_end="display")
    directives.mode(IAddForm, window_end="hidden")
    window_end = DatetimeField(
        title=_(u"Window End"),
        required=False,
        readonly=True,
    )

    notes = schema.TextLine(
        title=_(u"Notes"),
        required=False,
    )

    @invariant
    def validate_analysis_choice(data):
        spec = getattr(data, "analysis_specification", None)
        profile = getattr(data, "analysis_profile", None)
        if spec and profile:
            raise Invalid(_(u"Please select either an Analysis Specification or an Analysis Profile."))
        if not spec and not profile:
            raise Invalid(_(u"Please select one Analysis Specification or one Analysis Profile."))


@implementer(IStabilityTimepointTask, IStabilityTimepointTaskSchema)
class StabilityTimepointTask(Item):
    _catalogs = [SETUP_CATALOG]

