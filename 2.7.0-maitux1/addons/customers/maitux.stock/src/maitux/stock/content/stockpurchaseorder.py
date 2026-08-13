# -*- coding: utf-8 -*-
from decimal import Decimal

from bika.lims import bikaMessageFactory as _
from plone.supermodel import model
from plone.autoform import directives
from senaite.core.catalog import SETUP_CATALOG
from senaite.core.content.base import Item
from senaite.core.schema.datetimefield import DatetimeField
from senaite.core.schema.fields import DataGridField
from senaite.core.schema.fields import DataGridRow
from senaite.core.schema import UIDReferenceField
from z3c.form.interfaces import IFieldWidget
from z3c.form.widget import FieldWidget
from zope import schema
from zope.interface import implementer

from maitux.stock.interfaces import IStockPurchaseOrder
from maitux.stock.z3cform.widgets.datetimeseconds import DatetimeSecondsWidget
from maitux.stock.z3cform.widgets.purchaseorderlines import PurchaseOrderLinesWidgetFactory
from maitux.stock.z3cform.widgets.safeuidreference import SafeUIDReferenceWidgetFactory


@implementer(IFieldWidget)
def StockPurchaseOrderDateWidgetFactory(field, request):
    widget = DatetimeSecondsWidget(request)
    widget.show_time = True
    return FieldWidget(field, widget)


class IStockPurchaseOrderLineSchema(model.Schema):
    directives.widget(
        "stock",
        SafeUIDReferenceWidgetFactory,
        catalog="portal_catalog",
        multi_valued=False,
        clear_results_after_select=True,
        query={
            "is_active": True,
            "sort_on": "sortable_title",
            "sort_order": "ascending",
        },
    )
    stock = UIDReferenceField(
        title=u"Stock",
        allowed_types=("Stock", ),
        multi_valued=False,
        required=True,
    )

    supplier = schema.Choice(
        title=u"Supplier",
        vocabulary="maitux.stock.vocabularies.suppliers",
        required=False,
    )

    batch_number = schema.TextLine(
        title=u"Batch Number",
        required=False,
    )

    quantity_ordered = schema.Decimal(
        title=u"Quantity Ordered",
        required=True,
        min=Decimal("0.01"),
    )

    directives.widget(
        "unit",
        SafeUIDReferenceWidgetFactory,
        catalog=SETUP_CATALOG,
        multi_valued=False,
        clear_results_after_select=True,
        query={
            "is_active": True,
            "sort_on": "sortable_title",
            "sort_order": "ascending",
        },
    )
    unit = UIDReferenceField(
        title=u"Unit",
        allowed_types=("StockUnit", ),
        multi_valued=False,
        required=False,
    )

    unit_price = schema.Decimal(
        title=u"Unit Price",
        required=False,
    )

    batch = schema.TextLine(
        title=u"Batch",
        required=False,
    )

    tax_rate = schema.Decimal(
        title=u"Tax Rate",
        required=False,
    )


class IStockPurchaseOrderSchema(model.Schema):
    model.fieldset(
        "base_info",
        label=u"Base Information",
        fields=[
            "purchase_order_number",
            "purchaser",
            "order_date",
            "status",
            "remarks",
        ],
    )

    model.fieldset(
        "order_details",
        label=u"Order Details",
        fields=[
            "order_lines",
        ],
    )

    purchase_order_number = schema.TextLine(
        title=u"Purchase Order Number",
        required=True,
    )

    purchaser = schema.TextLine(
        title=u"Purchaser",
        required=False,
    )

    directives.widget("order_date", StockPurchaseOrderDateWidgetFactory)
    order_date = DatetimeField(
        title=u"Order Date",
        required=True,
    )

    status = schema.Choice(
        title=u"Status",
        values=(
            u"draft",
            u"submitted",
            u"received",
            u"cancelled",
        ),
        required=True,
        default=u"draft",
    )

    remarks = schema.Text(
        title=u"Remarks",
        required=False,
    )

    directives.widget("order_lines", PurchaseOrderLinesWidgetFactory)
    order_lines = DataGridField(
        title=u"Order Lines",
        required=False,
        value_type=DataGridRow(schema=IStockPurchaseOrderLineSchema),
        default=[],
    )


@implementer(IStockPurchaseOrder, IStockPurchaseOrderSchema)
class StockPurchaseOrder(Item):
    _catalogs = ["portal_catalog"]

