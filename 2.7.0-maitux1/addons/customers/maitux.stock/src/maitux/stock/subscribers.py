# -*- coding: utf-8 -*-
from decimal import Decimal

from bika.lims import api
from senaite.core.api import dtime
from senaite.core.interfaces import INumberGenerator
from senaite.core import logger
from zope.component import getUtility

from maitux.stock.stockbatchexpiry import REVIEW_STATE_ACTIVE
from maitux.stock.stockbatchexpiry import expire_batch
from maitux.stock.stockbatchexpiry import is_due_for_expiry
from maitux.stock.stockbatchexpiry import set_status_value


def _first_uid(value):
    if not value:
        return ""
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    value = api.safe_unicode(value)
    parts = value.splitlines()
    return parts[0] if parts else ""


def _get_next_batch_index(stock_number):
    """使用 Core 的带锁持久化计数器生成批次序号，保证并发安全"""
    key = "stockbatch-{}".format(stock_number)
    generator = getUtility(INumberGenerator)
    next_index = generator.get_number(key)
    if next_index in (None, ""):
        raise ValueError("Failed to generate batch index for '{}'".format(stock_number))
    return next_index


def stockbatch_added(stockbatch, event):
    if getattr(stockbatch, "portal_type", None) != "StockBatch":
        return

    now = dtime.now()
    user = api.get_current_user()
    user_id = user.getId() if user else ""

    if not getattr(stockbatch, "created_by", None):
        stockbatch.created_by = user_id
    if not getattr(stockbatch, "created_date", None):
        stockbatch.created_date = now
    set_status_value(stockbatch, REVIEW_STATE_ACTIVE)

    stock_uid = _first_uid(getattr(stockbatch, "stock", None))
    stock = api.get_object_by_uid(stock_uid, default=None) if stock_uid else None
    stock_number = getattr(stock, "number", None) if stock else None
    stock_number = api.safe_unicode(stock_number) if stock_number else u""

    if stock_number and not getattr(stockbatch, "batch_id", None):
        # 批次编号是核心业务字段，生成失败时直接抛错，避免落库空编号。
        idx = _get_next_batch_index(stock_number)
        stockbatch.batch_id = u"{}/{}".format(stock_number, idx)
        stockbatch.title = stockbatch.batch_id
        logger.info("Generated StockBatch batch_id '%s'", stockbatch.batch_id)

    if not getattr(stockbatch, "usage_records", None):
        qty = getattr(stockbatch, "current_amount", None)
        try:
            qty = Decimal(qty) if qty is not None else Decimal("0.00")
        except Exception:
            qty = Decimal("0.00")
        # Auto-populate from selected Stock's quantity if not provided
        try:
            if qty == Decimal("0.00"):
                stock_uid = _first_uid(getattr(stockbatch, "stock", None))
                stock = api.get_object_by_uid(stock_uid, default=None) if stock_uid else None
                if stock:
                    sval = getattr(stock, "quantity", None)
                    if sval is not None:
                        sval = Decimal(sval)
                        stockbatch.current_amount = sval
                        qty = sval
        except Exception:
            pass
        # Set target quantity at creation
        try:
            if not getattr(stockbatch, "target_quantity", None):
                stockbatch.target_quantity = qty
        except Exception:
            pass
        stockbatch.usage_records = [{
            "operation_type": u"create",
            "operator": api.safe_unicode(user_id),
            "operation_date": now,
            "quantity": qty,
            "remarks": u"",
            "from_batch": u"",
        }]

    try:
        stockbatch.reindexObject()
    except Exception:
        pass

    # 新建时如果有效期已经过去，立即补齐过期状态，避免落库后仍显示为可用。
    if is_due_for_expiry(stockbatch, now=now):
        try:
            expire_batch(
                stockbatch,
                now=now,
                operator=api.safe_unicode(user_id),
                remarks=u"Auto expired on create",
                reindex=True,
            )
        except Exception:
            logger.exception(
                "Failed to auto-expire StockBatch '%s' on create",
                api.get_uid(stockbatch),
            )
