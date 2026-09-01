# -*- coding: utf-8 -*-
from decimal import Decimal

from bika.lims.interfaces import IDeactivable
from plone.autoform import directives
from plone.supermodel import model
from senaite.core.catalog import SETUP_CATALOG
from senaite.core.content.base import Item
from senaite.core.schema.datetimefield import DatetimeField
from senaite.core.schema import TextLineField
from senaite.core.schema import UIDReferenceField
from senaite.core.z3cform.widgets.uidreference import UIDReferenceWidgetFactory
from z3c.form.interfaces import IFieldWidget
from z3c.form.widget import FieldWidget
from zope import schema
from zope.interface import implementer

from maitux.stock import _
from maitux.stock.interfaces import IStock
from maitux.stock.z3cform.widgets.datetimeseconds import DatetimeSecondsWidget


@implementer(IFieldWidget)
def StockExpiryDateWidgetFactory(field, request):
    widget = DatetimeSecondsWidget(request)
    widget.show_time = True
    return FieldWidget(field, widget)


class IStockSchema(model.Schema):
    number = TextLineField(
        title=_(u"Stock Number"),
        required=True,
    )

    directives.widget(
        "stock_type",
        UIDReferenceWidgetFactory,
        catalog=SETUP_CATALOG,
        query={
            "is_active": True,
            "sort_on": "sortable_title",
            "sort_order": "ascending",
        },
    )
    stock_type = UIDReferenceField(
        title=_(u"Stock Type"),
        allowed_types=("StockType", ),
        multi_valued=False,
        required=False,
    )

    directives.widget(
        "sample_matrix",
        UIDReferenceWidgetFactory,
        catalog=SETUP_CATALOG,
        query={
            "is_active": True,
            "sort_on": "sortable_title",
            "sort_order": "ascending",
        },
    )
    sample_matrix = UIDReferenceField(
        title=_(u"Name"),
        allowed_types=("SampleMatrix", ),
        multi_valued=False,
        required=False,
    )

    directives.widget(
        "unit",
        UIDReferenceWidgetFactory,
        catalog=SETUP_CATALOG,
        query={
            "is_active": True,
            "sort_on": "sortable_title",
            "sort_order": "ascending",
        },
    )
    unit = UIDReferenceField(
        title=_(u"Unit"),
        allowed_types=("StockUnit", ),
        multi_valued=False,
        required=False,
    )

    directives.widget(
        "location",
        UIDReferenceWidgetFactory,
        catalog=SETUP_CATALOG,
        query={
            "is_active": True,
            "sort_on": "sortable_title",
            "sort_order": "ascending",
        },
    )
    location = UIDReferenceField(
        title=_(u"Storage Location"),
        allowed_types=("InstrumentLocation", ),
        multi_valued=False,
        required=False,
    )

    directives.widget(
        "supplier",
        UIDReferenceWidgetFactory,
        catalog=SETUP_CATALOG,
        query={
            "is_active": True,
            "sort_on": "sortable_title",
            "sort_order": "ascending",
        },
    )
    supplier = UIDReferenceField(
        title=_(u"Supplier"),
        allowed_types=("Supplier", ),
        multi_valued=True,
        required=False,
    )

    quantity = schema.Decimal(
        title=_(u"Quantity"),
        required=True,
        default=Decimal("0.00"),
    )

    directives.widget("expiry_date", StockExpiryDateWidgetFactory)
    expiry_date = DatetimeField(
        title=_(u"Expiry Date"),
        required=False,
    )


@implementer(IStock, IStockSchema, IDeactivable)
class Stock(Item):
    _catalogs = ["portal_catalog"]

    def Title(self):
        number = getattr(self, "number", None)
        if number:
            return number
        return super(Stock, self).Title()

