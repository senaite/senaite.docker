# -*- coding: utf-8 -*-
from plone.autoform import directives
from plone.namedfile.field import NamedBlobFile
from plone.supermodel import model
from senaite.core.catalog import SETUP_CATALOG
from senaite.core.catalog import SENAITE_CATALOG
from senaite.core.config.widgets import get_default_columns
from senaite.core.content.base import Container
from senaite.core.schema import DatetimeField
from senaite.core.schema.fields import DataGridField
from senaite.core.schema.fields import DataGridRow
from senaite.core.schema import IntField
from senaite.core.schema import UIDReferenceField
from senaite.core.z3cform.widgets.uidreference import UIDReferenceWidgetFactory
from z3c.form.interfaces import IAddForm
from zope import schema
from zope.interface import implementer
from zope.interface import Invalid
from zope.interface import invariant
from zope.schema.vocabulary import SimpleTerm
from zope.schema.vocabulary import SimpleVocabulary

from maitux.stability import _
from maitux.stability.interfaces import IStabilityPlan
from maitux.stability.z3cform.widgets.plandetails import PlanDetailsWidgetFactory
from maitux.stability.z3cform.widgets.plandetails import SafeUIDReferenceWidgetFactory


ORIENTATION_VOCABULARY = SimpleVocabulary((
    SimpleTerm(value=u"upright", token="upright", title=_(u"Upright")),
    SimpleTerm(value=u"inverted", token="inverted", title=_(u"Inverted")),
    SimpleTerm(value=u"horizontal", token="horizontal", title=_(u"Horizontal")),
))

PLAN_STATUS_VOCABULARY = SimpleVocabulary((
    SimpleTerm(value=u"active", token="active", title=_(u"Active")),
    SimpleTerm(value=u"inactive", token="inactive", title=_(u"Inactive")),
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


class IStabilityPlanDetailSchema(model.Schema):
    directives.widget(
        "packaging_specification",
        SafeUIDReferenceWidgetFactory,
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
        SafeUIDReferenceWidgetFactory,
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
        SafeUIDReferenceWidgetFactory,
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
        SafeUIDReferenceWidgetFactory,
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

    directives.mode(analysis_request="hidden")
    directives.widget(
        "analysis_request",
        UIDReferenceWidgetFactory,
        catalog="portal_catalog",
        query={
            "portal_type": "AnalysisRequest",
            "sort_on": "created",
            "sort_order": "descending",
        },
        display_template="<a href='${url}'>${Title}</a>",
        columns=get_default_columns,
    )
    analysis_request = UIDReferenceField(
        title=_(u"Sample"),
        allowed_types=("AnalysisRequest",),
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
        SafeUIDReferenceWidgetFactory,
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

    directives.mode(detail_status="hidden")
    detail_status = schema.Choice(
        title=_(u"Status"),
        vocabulary=DETAIL_STATUS_VOCABULARY,
        required=True,
        default=u"pending_placement",
    )

    notes = schema.TextLine(
        title=_(u"Notes"),
        required=False,
    )

    @invariant
    def validate_analysis_choice(data):
        spec = getattr(data, "analysis_specification", None)
        profile = getattr(data, "analysis_profile", None)
        # 计划明细和任务对象保持同一条业务规则，避免两边保存口径不一致。
        if spec and profile:
            raise Invalid(_(u"Please select either an Analysis Specification or an Analysis Profile."))
        if not spec and not profile:
            raise Invalid(_(u"Please select one Analysis Specification or one Analysis Profile."))


class IStabilityPlanSchema(model.Schema):
    model.fieldset(
        "plan_details",
        label=_(u"Plan Details"),
        fields=[
            "plan_details",
        ],
    )

    title = schema.TextLine(
        title=_(u"Stability Study Name"),
        required=True,
    )

    description = schema.Text(
        title=_(u"Description"),
        required=False,
    )

    directives.mode(plan_id="display")
    directives.mode(IAddForm, plan_id="hidden")
    plan_id = schema.TextLine(
        title=_(u"Stability Study Plan ID"),
        required=False,
        readonly=True,
    )

    directives.mode(status="display")
    directives.mode(IAddForm, status="hidden")
    status = schema.Choice(
        title=_(u"Status"),
        vocabulary=PLAN_STATUS_VOCABULARY,
        required=False,
        default=u"active",
    )

    directives.widget(
        "plan_template",
        UIDReferenceWidgetFactory,
        catalog=SETUP_CATALOG,
        query={
            "portal_type": "StabilityPlanTemplate",
            "is_active": True,
            "sort_on": "sortable_title",
            "sort_order": "ascending",
        },
        display_template="<a href='${url}'>${Title}</a>",
        columns=get_default_columns,
    )
    directives.mode(plan_template="hidden")
    plan_template = UIDReferenceField(
        title=_(u"Plan Template"),
        allowed_types=("StabilityPlanTemplate",),
        multi_valued=False,
        required=True,
    )

    start_time = DatetimeField(
        title=_(u"Start Time (T0)"),
        required=True,
    )

    sample_quantity = IntField(
        title=_(u"Storage Quantity - Sampling"),
        required=False,
        default=0,
    )

    reserve_quantity = IntField(
        title=_(u"Storage Quantity - Reserve"),
        required=False,
        default=0,
    )

    directives.mode(total_quantity="display")
    directives.mode(IAddForm, total_quantity="hidden")
    total_quantity = IntField(
        title=_(u"Storage Quantity - Total"),
        required=False,
        default=0,
        readonly=True,
    )

    directives.widget(
        "unit",
        UIDReferenceWidgetFactory,
        catalog=SETUP_CATALOG,
        query={
            "portal_type": "StockUnit",
            "is_active": True,
            "sort_on": "sortable_title",
            "sort_order": "ascending",
        },
        display_template="<a href='${url}'>${Title}</a>",
        columns=get_default_columns,
    )
    unit = UIDReferenceField(
        title=_(u"Unit"),
        allowed_types=("StockUnit",),
        multi_valued=False,
        required=False,
    )

    article = NamedBlobFile(
        title=_(u"Article"),
        required=False,
    )

    directives.widget(
        "plan_details",
        PlanDetailsWidgetFactory,
        allow_insert=True,
        allow_delete=True,
        allow_reorder=True,
        auto_append=False,
    )
    plan_details = DataGridField(
        title=_(u"Plan Details"),
        required=False,
        value_type=DataGridRow(schema=IStabilityPlanDetailSchema),
        default=[],
    )


@implementer(IStabilityPlan, IStabilityPlanSchema)
class StabilityPlan(Container):
    _catalogs = [SETUP_CATALOG]

