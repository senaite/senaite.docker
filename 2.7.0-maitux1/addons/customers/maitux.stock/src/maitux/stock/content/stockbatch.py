# -*- coding: utf-8 -*-
from decimal import Decimal

from plone.autoform import directives
from plone.supermodel import model
from senaite.core.catalog import SETUP_CATALOG
from senaite.core.content.base import Item
from senaite.core.schema.datetimefield import DatetimeField
from senaite.core.schema.fields import DataGridField
from senaite.core.schema.fields import DataGridRow
from senaite.core.schema import UIDReferenceField
from z3c.form.interfaces import IFieldWidget
from z3c.form.interfaces import IAddForm
from z3c.form.interfaces import IEditForm
from z3c.form.widget import FieldWidget
from zope import schema
from zope.interface import implementer

from maitux.stock.interfaces import IStockBatch
from maitux.stock.z3cform.widgets.datetimeseconds import DatetimeSecondsWidget
from maitux.stock.z3cform.widgets.safeuidreference import SafeUIDReferenceWidgetFactory
from maitux.stock.z3cform.widgets.stockbatchamount import StockBatchAmountWidgetFactory


@implementer(IFieldWidget)
def StockBatchExpiryDateWidgetFactory(field, request):
    widget = DatetimeSecondsWidget(request)
    widget.show_time = True
    return FieldWidget(field, widget)


@implementer(IFieldWidget)
def StockBatchCreatedDateWidgetFactory(field, request):
    widget = DatetimeSecondsWidget(request)
    widget.show_time = True
    return FieldWidget(field, widget)


@implementer(IFieldWidget)
def StockBatchOperationDateWidgetFactory(field, request):
    widget = DatetimeSecondsWidget(request)
    widget.show_time = True
    return FieldWidget(field, widget)


class IStockBatchUsageSchema(model.Schema):
    operation_type = schema.Choice(
        title=u"Operation Type",
        values=(
            u"create",
            u"consume",
            u"expire",
            u"return",
            u"destroy",
            u"split",
            u"adjust",
            u"stocktake",
        ),
        required=True,
        default=u"create",
    )

    operator = schema.TextLine(
        title=u"Operator",
        required=True,
    )

    directives.widget("operation_date", StockBatchOperationDateWidgetFactory)
    operation_date = DatetimeField(
        title=u"Operation Date",
        required=True,
    )

    quantity = schema.Decimal(
        title=u"Quantity",
        required=True,
        default=Decimal("0.00"),
    )

    remarks = schema.TextLine(
        title=u"Remarks",
        required=False,
    )

    from_batch = schema.TextLine(
        title=u"From Batch",
        required=False,
    )


class IStockBatchSchema(model.Schema):
    model.fieldset(
        "batch_details",
        label=u"Batch Details",
        fields=[
            "supplier",
            "batch",
            "current_amount",
            "low_quantity_threshold",
            "unit",
            "expiry_date",
            "location",
        ],
    )

    model.fieldset(
        "usage",
        label=u"Usage Records",
        fields=[
            "usage_records",
        ],
    )

    directives.mode(created_by="display")
    directives.mode(IAddForm, created_by="hidden")
    created_by = schema.TextLine(
        title=u"Created By",
        required=False,
        readonly=True,
    )

    directives.mode(created_date="display")
    directives.mode(IAddForm, created_date="hidden")
    directives.widget("created_date", StockBatchCreatedDateWidgetFactory)
    created_date = DatetimeField(
        title=u"Created Date",
        required=False,
        readonly=True,
    )

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
        allowed_types=("Stock",),
        multi_valued=False,
        required=True,
    )

    directives.mode(batch_id="display")
    directives.mode(IAddForm, batch_id="hidden")
    batch_id = schema.TextLine(
        title=u"Batch ID",
        required=False,
        readonly=True,
    )

    description = schema.Text(
        title=u"Description",
        required=False,
    )

    status = schema.Choice(
        title=u"Status",
        values=(
            u"active",
            u"expired",
            u"inactive",
            u"destroyed",
        ),
        required=True,
        default=u"active",
    )
    directives.mode(IAddForm, status="hidden")

    supplier = schema.Choice(
        title=u"Supplier",
        vocabulary="maitux.stock.vocabularies.suppliers",
        required=False,
    )

    batch = schema.TextLine(
        title=u"Batch",
        required=False,
    )

    directives.widget("current_amount", StockBatchAmountWidgetFactory)
    current_amount = schema.Decimal(
        title=u"Current Amount",
        required=True,
        default=Decimal("0.00"),
        min=Decimal("0"),  # 防止创建负数库存批次
    )

    low_quantity_threshold = schema.Decimal(
        title=u"Low Quantity Threshold",
        required=False,
    )

    directives.mode(target_quantity="display")
    directives.mode(IAddForm, target_quantity="hidden")
    directives.mode(IEditForm, target_quantity="hidden")
    target_quantity = schema.Decimal(
        title=u"Target Quantity",
        required=False,
        default=Decimal("0.00"),
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
        allowed_types=("StockUnit",),
        multi_valued=False,
        required=False,
    )

    directives.widget("expiry_date", StockBatchExpiryDateWidgetFactory)
    expiry_date = DatetimeField(
        title=u"Expiry Date",
        required=False,
    )

    directives.widget(
        "location",
        SafeUIDReferenceWidgetFactory,
        catalog=SETUP_CATALOG,
        multi_valued=False,
        clear_results_after_select=True,
        query={
            "portal_type": "InstrumentLocation",
            "is_active": True,
            "sort_on": "sortable_title",
            "sort_order": "ascending",
        },
    )
    location = UIDReferenceField(
        title=u"Location",
        allowed_types=("InstrumentLocation",),
        multi_valued=False,
        required=False,
    )

    directives.mode(usage_records="display")
    directives.mode(IAddForm, usage_records="hidden")
    usage_records = DataGridField(
        title=u"Usage Records",
        required=False,
        value_type=DataGridRow(schema=IStockBatchUsageSchema),
        default=[],
    )


@implementer(IStockBatch, IStockBatchSchema)
class StockBatch(Item):
    _catalogs = ["portal_catalog"]

    def getBatchID(self):
        val = getattr(self, "batch_id", "") or ""
        if not val:
            try:
                val = self.Title()
            except Exception:
                val = ""
        return val

