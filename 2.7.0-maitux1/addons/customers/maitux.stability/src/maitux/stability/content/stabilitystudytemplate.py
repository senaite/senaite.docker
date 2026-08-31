# -*- coding: utf-8 -*-
from bika.lims.interfaces import IDeactivable
from plone.autoform import directives
from plone.namedfile.field import NamedBlobFile
from plone.supermodel import model
from senaite.core.catalog import SETUP_CATALOG
from senaite.core.config.widgets import get_default_columns
from senaite.core.content.base import Container
from senaite.core.schema import IntField
from senaite.core.schema import UIDReferenceField
from senaite.core.z3cform.widgets.uidreference import UIDReferenceWidgetFactory
from persistent.list import PersistentList
from z3c.form.interfaces import IAddForm
from zope import schema
from zope.interface import implementer

from maitux.stability import _
from maitux.stability.interfaces import IStabilityPlanTemplate



class IStabilityStudyTemplateSchema(model.Schema):
    title = schema.TextLine(
        title=_(u"Study Name"),
        required=True,
    )

    description = schema.Text(
        title=_(u"Description"),
        required=False,
    )

    directives.mode(study_plan_id="display")
    directives.mode(IAddForm, study_plan_id="hidden")
    study_plan_id = schema.TextLine(
        title=_(u"Stability Study Plan ID"),
        required=False,
        readonly=True,
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

class IStabilityPlanTemplateSchema(IStabilityStudyTemplateSchema):
    pass


@implementer(IStabilityPlanTemplate, IStabilityPlanTemplateSchema, IDeactivable)
class StabilityPlanTemplate(Container):
    _catalogs = [SETUP_CATALOG]

    def _ensure_ordering(self):
        for name in ("_ordering", "_order"):
            if getattr(self, name, None) is None:
                try:
                    setattr(self, name, PersistentList())
                except Exception:
                    pass

    def __contains__(self, name):
        self._ensure_ordering()
        try:
            return super(StabilityPlanTemplate, self).__contains__(name)
        except TypeError:
            try:
                return self._getOb(name, default=None) is not None
            except Exception:
                return False

