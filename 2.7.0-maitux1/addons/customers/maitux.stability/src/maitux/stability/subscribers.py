# -*- coding: utf-8 -*-
from datetime import timedelta

from bika.lims import api
from plone import api as ploneapi
from senaite.core import logger
from senaite.core.upgrade.utils import temporary_allow_type
from zope.annotation.interfaces import IAnnotations


def _normalize_quantity(value):
    return value or 0


def _first(value):
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _normalize_months(value):
    """统一把时间点月份转换为非负整数，兼容下拉回传的字符串值。"""
    try:
        value = int(value)
    except Exception:
        return 0
    return value if value >= 0 else 0


def _plan_log_label(plan):
    """生成日志可读标签，便于定位是哪一个计划的哪一行数据。"""
    try:
        return api.get_path(plan)
    except Exception:
        return api.get_id(plan) or repr(plan)


def _resolve_uid_reference(value, allowed_type, field_name, plan=None, sequence=None):
    """解析并校验 UID 引用，非法值返回 None 并记录日志。

    这里不抛异常，避免单个无效引用阻断整条任务创建链路。
    """
    candidate = _first(value)
    if not candidate:
        return None

    obj = candidate if api.is_object(candidate) else None
    uid = api.get_uid(obj) if obj is not None else candidate

    if not api.is_uid(uid):
        logger.warning(
            "Skip invalid %s reference for plan '%s' seq %s: %r is not a UID",
            field_name, _plan_log_label(plan), sequence, candidate)
        return None

    if obj is None:
        try:
            obj = api.get_object_by_uid(uid)
        except Exception:
            obj = None

    if not api.is_object(obj):
        logger.warning(
            "Skip missing %s reference for plan '%s' seq %s: %r",
            field_name, _plan_log_label(plan), sequence, uid)
        return None

    if api.get_portal_type(obj) != allowed_type:
        logger.warning(
            "Skip invalid %s reference for plan '%s' seq %s: expected %s, got %s",
            field_name, _plan_log_label(plan), sequence,
            allowed_type, api.get_portal_type(obj))
        return None

    return api.get_uid(obj) or uid


def _sync_template_fields(obj):
    changed = False

    plan_id = api.get_id(obj)
    if plan_id and getattr(obj, "study_plan_id", None) != plan_id:
        obj.study_plan_id = plan_id
        changed = True

    total = (
        _normalize_quantity(getattr(obj, "sample_quantity", None)) +
        _normalize_quantity(getattr(obj, "reserve_quantity", None))
    )
    if getattr(obj, "total_quantity", None) != total:
        obj.total_quantity = total
        changed = True

    if changed:
        obj.reindexObject()


def _sync_plan_fields(obj):
    if api.get_portal_type(obj) != "StabilityPlan":
        return False

    changed = False

    plan_id = api.get_id(obj)
    if plan_id and getattr(obj, "plan_id", None) != plan_id:
        obj.plan_id = plan_id
        changed = True

    total = (
        _normalize_quantity(getattr(obj, "sample_quantity", None)) +
        _normalize_quantity(getattr(obj, "reserve_quantity", None))
    )
    if getattr(obj, "total_quantity", None) != total:
        obj.total_quantity = total
        changed = True

    if changed:
        obj.reindexObject()

    return changed


def _generate_plan_timepoint_tasks(plan):
    if api.get_portal_type(plan) != "StabilityPlan":
        return False

    key = "maitux.stability.tasks_generated"
    try:
        annotations = IAnnotations(plan)
    except Exception:
        annotations = None

    existing = []
    try:
        for child in plan.objectValues():
            if api.get_portal_type(child) == "StabilityTimepointTask":
                existing.append(child)
    except Exception:
        existing = []

    if existing:
        if annotations is not None:
            annotations[key] = True
        return False

    if annotations is not None and annotations.get(key):
        return False

    plan_details = getattr(plan, "plan_details", None) or []
    detail_rows = []
    for idx, row in enumerate(plan_details, start=1):
        if not isinstance(row, dict):
            continue
        detail_rows.append((idx, row))

    if not detail_rows:
        return False

    start_time = getattr(plan, "start_time", None)

    created = False
    for idx, tp in enumerate(detail_rows, start=1):
        row = tp[1]
        seq = idx
        months = _normalize_months(row.get("timepoint_days"))

        window_months = row.get("window_days")
        if not isinstance(window_months, int) or window_months < 0:
            window_months = 0

        base_id = "tp-{0:03d}".format(seq)
        obj_id = base_id
        suffix = 1
        while getattr(plan, "get", lambda _id: None)(obj_id) is not None:
            obj_id = "{0}-{1}".format(base_id, suffix)
            suffix += 1

        # 时间点单位为 Months，窗口期单位为 Days。
        title = "TP {0} ({1} Months)".format(seq, months)

        with temporary_allow_type(plan, "StabilityTimepointTask"):
            task = ploneapi.content.create(
                container=plan,
                type="StabilityTimepointTask",
                id=obj_id,
                title=title,
            )

        task.sequence = seq
        task.timepoint_days = months
        task.window_days = window_months

        task.packaging_specification = _first(row.get("packaging_specification"))
        task.storage_condition = _first(row.get("storage_condition"))
        task.orientation = row.get("orientation")
        task.analysis_specification = _first(row.get("analysis_specification"))
        task.analysis_profile = _first(row.get("analysis_profile"))
        task.batch = _first(row.get("batch"))
        # StockBatch 引用可能已经失效，这里降级为 None 并记录日志，
        # 避免单个无效引用导致整个时间点任务生成中断。
        task.stock_batch = _resolve_uid_reference(
            row.get("stock_batch"), "StockBatch", "stock_batch", plan, seq)
        task.inspection_quantity = _normalize_quantity(row.get("inspection_quantity"))
        task.detail_status = row.get("detail_status") or "pending_placement"
        task.notes = row.get("notes")

        if start_time:
            # 时间点按月计算，约定 1 月 = 30 天。
            target = start_time + timedelta(days=months * 30)
            if window_months:
                # 窗口期直接使用天数。
                w_start = target - timedelta(days=window_months)
                w_end = target + timedelta(days=window_months)
            else:
                w_start = target
                w_end = target
            task.target_date = target
            task.window_start = w_start
            task.window_end = w_end

        task.reindexObject()
        created = True

    if created and annotations is not None:
        annotations[key] = True

    return created


def sync_plan_timepoint_tasks(plan, delete_excess=True):
    """把 StabilityPlan.plan_details 同步到已生成的 StabilityTimepointTask。

    同步策略尽量保守：
    - 仅对 `detail_status=pending_placement` 的任务做更新/删除
    - 对 plan_details 中新增的时间点，创建新的任务
    - 对 plan_details 中移除的时间点，删除对应的 pending_placement 任务
    """
    if api.get_portal_type(plan) != "StabilityPlan":
        return (0, 0, 0)

    plan_details = getattr(plan, "plan_details", None) or []
    desired = []
    for idx, row in enumerate(plan_details, start=1):
        if not isinstance(row, dict):
            continue
        desired.append((idx, row))

    desired_seqs = set([seq for seq, _row in desired])

    existing = []
    try:
        for child in plan.objectValues():
            if api.get_portal_type(child) == "StabilityTimepointTask":
                existing.append(child)
    except Exception:
        existing = []

    by_seq = {}
    for task in existing:
        seq = getattr(task, "sequence", None)
        if isinstance(seq, int) and seq > 0:
            by_seq[seq] = task

    start_time = getattr(plan, "start_time", None)

    created = 0
    updated = 0
    deleted = 0

    def apply_row_to_task(task, seq, row):
        """将行数据写入任务对象，仅用于 pending_placement。"""
        months = _normalize_months(row.get("timepoint_days", 0))
        window_days = row.get("window_days", 0)
        if not isinstance(window_days, int) or window_days < 0:
            window_days = 0

        task.sequence = seq
        task.timepoint_days = months
        task.window_days = window_days

        task.packaging_specification = _first(row.get("packaging_specification"))
        task.storage_condition = _first(row.get("storage_condition"))
        task.orientation = row.get("orientation") or getattr(task, "orientation", None)
        task.analysis_specification = _first(row.get("analysis_specification"))
        task.analysis_profile = _first(row.get("analysis_profile"))
        task.batch = _first(row.get("batch"))
        # 同步时同样要容忍已失效的 StockBatch 引用，避免整个任务同步失败。
        task.stock_batch = _resolve_uid_reference(
            row.get("stock_batch"), "StockBatch", "stock_batch", plan, seq)
        task.inspection_quantity = _normalize_quantity(row.get("inspection_quantity"))
        task.notes = row.get("notes") or ""

        # 时间点单位为月：目标日期 = T0 + (Months * 30 天)。
        if start_time:
            target = start_time + timedelta(days=months * 30)
            w_start = target - timedelta(days=window_days) if window_days else target
            w_end = target + timedelta(days=window_days) if window_days else target
            task.target_date = target
            task.window_start = w_start
            task.window_end = w_end

        # 标题统一使用 Months，例如：TP 1 (3 Months)。
        task.title = "TP {0} ({1} Months)".format(seq, months)

    # 先完成全部创建/更新，再删除多余任务，避免中途失败导致 pending 任务丢失。
    sync_ok = True

    # 更新或创建任务。
    for seq, row in desired:
        created_now = False
        task = None
        task = by_seq.get(seq)
        try:
            if task is None:
                base_id = "tp-{0:03d}".format(seq)
                obj_id = base_id
                suffix = 1
                while getattr(plan, "get", lambda _id: None)(obj_id) is not None:
                    obj_id = "{0}-{1}".format(base_id, suffix)
                    suffix += 1

                months = _normalize_months(row.get("timepoint_days", 0))
                title = "TP {0} ({1} Months)".format(seq, months)

                with temporary_allow_type(plan, "StabilityTimepointTask"):
                    task = ploneapi.content.create(
                        container=plan,
                        type="StabilityTimepointTask",
                        id=obj_id,
                        title=title,
                    )
                by_seq[seq] = task
                created += 1
                created_now = True

            status = getattr(task, "detail_status", None) or "pending_placement"
            if status != "pending_placement":
                continue

            apply_row_to_task(task, seq, row)
            task.reindexObject()
            updated += 1
        except Exception:
            sync_ok = False
            logger.exception(
                "Failed to sync pending timepoint task for plan '%s' seq %s",
                _plan_log_label(plan), seq)
            # 新建任务失败时尽量回滚本次新增对象，避免留下半成品任务。
            if created_now and api.is_object(task):
                try:
                    ploneapi.content.delete(obj=task)
                    created -= 1
                except Exception:
                    logger.exception(
                        "Failed to rollback newly created task for plan '%s' seq %s",
                        _plan_log_label(plan), seq)
            continue

    # 删除多余的 pending_placement 任务。
    if delete_excess and sync_ok:
        for task in list(existing):
            status = getattr(task, "detail_status", None) or "pending_placement"
            if status != "pending_placement":
                continue
            seq = getattr(task, "sequence", None)
            if isinstance(seq, int) and seq > 0 and seq not in desired_seqs:
                try:
                    ploneapi.content.delete(obj=task)
                    deleted += 1
                except Exception:
                    logger.exception(
                        "Failed to delete excess pending task for plan '%s' seq %s",
                        _plan_log_label(plan), seq)
    elif delete_excess and not sync_ok:
        logger.warning(
            "Skip deletion phase for plan '%s' because create/update phase was not fully successful",
            _plan_log_label(plan))

    return (created, updated, deleted)


def stability_study_template_added(obj, event):
    _sync_template_fields(obj)


def stability_study_template_modified(obj, event):
    _sync_template_fields(obj)


stability_plan_template_added = stability_study_template_added
stability_plan_template_modified = stability_study_template_modified


def stability_plan_added(obj, event):
    _sync_plan_fields(obj)
    _generate_plan_timepoint_tasks(obj)


def stability_plan_modified(obj, event):
    _sync_plan_fields(obj)
