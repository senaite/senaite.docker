# -*- coding: utf-8 -*-
from decimal import Decimal

from bika.lims import api
from DateTime import DateTime
from Products.CMFCore.WorkflowCore import WorkflowException
from senaite.core import logger
from senaite.core.api import dtime


REVIEW_STATE_ACTIVE = u"active"
REVIEW_STATE_EXPIRED = u"expired"
REVIEW_STATE_DESTROYED = u"destroyed"
EXPIRED_REMARK = u"Auto expired by scheduler"
STOCKBATCH_WORKFLOW_ID = "senaite_stockbatch_workflow"


def get_review_state(batch):
    """返回批次当前工作流状态。"""
    return api.safe_unicode(api.get_review_status(batch) or u"").strip()


def get_status_value(batch):
    """返回批次 schema 中的状态字段值。"""
    return api.safe_unicode(getattr(batch, "status", u"") or u"").strip()


def set_status_value(batch, state):
    """同步 schema 状态字段，避免 catalog/status 与工作流状态不一致。"""
    if not api.is_object(batch):
        return False
    state = api.safe_unicode(state or u"").strip()
    current = get_status_value(batch)
    if current == state:
        return False
    batch.status = state
    return True


def get_expiry_ansi(batch):
    """把 expiry_date 统一转成 ANSI 字符串，便于安全比较。"""
    expiry = getattr(batch, "expiry_date", None)
    if not expiry:
        return u""
    try:
        return api.safe_unicode(dtime.to_ansi(expiry, show_time=True) or u"")
    except Exception:
        logger.warning("Failed to convert expiry_date for batch '%s'", api.get_uid(batch))
        return u""


def is_due_for_expiry(batch, now=None):
    """判断批次是否已经到达或超过失效时间。"""
    if not api.is_object(batch):
        return False
    if get_review_state(batch) == REVIEW_STATE_DESTROYED:
        return False
    expiry_ansi = get_expiry_ansi(batch)
    if not expiry_ansi:
        return False
    if now is None:
        now = dtime.now()
    now_ansi = api.safe_unicode(dtime.to_ansi(now, show_time=True) or u"")
    if not now_ansi:
        return False
    return expiry_ansi <= now_ansi


def get_operation_block_message(batch, now=None):
    """返回当前批次是否禁止继续业务操作的提示。"""
    state = get_review_state(batch)
    if state == REVIEW_STATE_DESTROYED:
        return u"Batch is destroyed"
    if state == REVIEW_STATE_EXPIRED or is_due_for_expiry(batch, now=now):
        return u"Batch is expired and can only be destroyed"
    return u""


def append_usage_record(batch, operation_type, operator, operation_date,
                        quantity=None, remarks=u"", from_batch=u""):
    """追加库存流水，保留状态变化轨迹。"""
    records = getattr(batch, "usage_records", None) or []
    if not isinstance(records, (list, tuple)):
        records = []
    records = list(records)
    try:
        quantity = Decimal(quantity) if quantity is not None else Decimal("0.00")
    except Exception:
        quantity = Decimal("0.00")
    records.append({
        "operation_type": api.safe_unicode(operation_type or u""),
        "operator": api.safe_unicode(operator or u""),
        "operation_date": operation_date,
        "quantity": quantity,
        "remarks": api.safe_unicode(remarks or u""),
        "from_batch": api.safe_unicode(from_batch or u""),
    })
    batch.usage_records = records


def expire_batch(batch, workflow_tool=None, now=None, operator=u"",
                 remarks=None, reindex=True):
    """把批次切换为过期状态，并同步状态字段。"""
    if not api.is_object(batch):
        return False
    if now is None:
        now = dtime.now()
    state = get_review_state(batch)
    if state == REVIEW_STATE_DESTROYED:
        set_status_value(batch, REVIEW_STATE_DESTROYED)
        return False
    if state == REVIEW_STATE_EXPIRED:
        changed = set_status_value(batch, REVIEW_STATE_EXPIRED)
        if changed and reindex:
            batch.reindexObject()
        return False
    if not is_due_for_expiry(batch, now=now):
        return False
    if workflow_tool is None:
        workflow_tool = api.get_tool("portal_workflow")
    if workflow_tool is None:
        raise RuntimeError("portal_workflow tool not found")

    try:
        workflow_tool.doActionFor(batch, "expire", comment=remarks or EXPIRED_REMARK)
    except WorkflowException:
        # 兼容安装/升级阶段旧工作流定义尚未刷新完成的场景：
        # 若当前站点还没有 expire transition，则直接补写 review_state。
        workflow_tool.setStatusOf(
            STOCKBATCH_WORKFLOW_ID,
            batch,
            {
                "review_state": REVIEW_STATE_EXPIRED,
                "action": "expire",
                "actor": operator or "system",
                "time": DateTime(),
                "comments": remarks or EXPIRED_REMARK,
            },
        )
        workflow_definition = workflow_tool.getWorkflowById(STOCKBATCH_WORKFLOW_ID)
        if workflow_definition is not None:
            workflow_definition.updateRoleMappingsFor(batch)
    set_status_value(batch, REVIEW_STATE_EXPIRED)
    # 过期不改变数量，但记录当时剩余量，便于后续审计。
    append_usage_record(
        batch,
        operation_type=u"expire",
        operator=operator,
        operation_date=now,
        quantity=getattr(batch, "current_amount", None),
        remarks=remarks or EXPIRED_REMARK,
    )
    if reindex:
        batch.reindexObject()
    logger.info("Expired StockBatch '%s'", api.get_uid(batch))
    return True


def sync_expired_batches(context, limit=None, dry_run=False, now=None):
    """扫描并同步所有已过期的库存批次。"""
    if now is None:
        now = dtime.now()
    portal = api.get_portal()
    workflow_tool = api.get_tool("portal_workflow")
    catalog = api.get_tool("portal_catalog")
    if workflow_tool is None or catalog is None:
        raise RuntimeError("portal_workflow or portal_catalog tool not found")

    checked = 0
    expired = 0
    status_synced = 0
    errors = []
    brains = catalog(portal_type="StockBatch")
    for brain in brains:
        if limit and checked >= limit:
            break
        batch = brain.getObject()
        if not api.is_object(batch):
            continue
        checked += 1
        state = get_review_state(batch)
        try:
            if state == REVIEW_STATE_DESTROYED:
                if not dry_run and set_status_value(batch, REVIEW_STATE_DESTROYED):
                    batch.reindexObject()
                    status_synced += 1
                continue
            if state == REVIEW_STATE_EXPIRED:
                if not dry_run and set_status_value(batch, REVIEW_STATE_EXPIRED):
                    batch.reindexObject()
                    status_synced += 1
                continue
            if not is_due_for_expiry(batch, now=now):
                if not dry_run and state == REVIEW_STATE_ACTIVE:
                    if set_status_value(batch, REVIEW_STATE_ACTIVE):
                        batch.reindexObject()
                        status_synced += 1
                continue
            if dry_run:
                expired += 1
                continue
            if expire_batch(
                batch,
                workflow_tool=workflow_tool,
                now=now,
                operator=u"system",
                remarks=EXPIRED_REMARK,
                reindex=True,
            ):
                expired += 1
        except Exception as exc:
            uid = api.get_uid(batch)
            errors.append((uid, api.safe_unicode(exc)))
            logger.exception("Failed to sync expired StockBatch '%s'", uid)

    return {
        "checked": checked,
        "expired": expired,
        "status_synced": status_synced,
        "errors": errors,
        "dry_run": bool(dry_run),
    }
