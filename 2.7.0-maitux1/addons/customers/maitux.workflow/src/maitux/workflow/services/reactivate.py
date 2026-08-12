# -*- coding: utf-8 -*-
"""已发布样品/测试重新激活服务。"""

from collections import OrderedDict
import json

from bika.lims import api
from bika.lims.api.snapshot import get_storage
from bika.lims.api.snapshot import take_snapshot
from bika.lims.api.user import get_user_id
from bika.lims.subscribers.auditlog import reindex_object
from bika.lims.utils import changeWorkflowState
from Products.CMFCore.WorkflowCore import WorkflowException


ANALYSIS_PORTAL_TYPES = (
    "Analysis",
)

SAMPLE_PORTAL_TYPES = (
    "AnalysisRequest",
)

WORKSHEET_WORKFLOW_ID = "senaite_worksheet_workflow"
REACTIVATE_REASON_FIELD = u"重新激活原因"

WORKSHEET_ROLLBACK_TRANSITIONS = {
    "to_be_verified": "rollback_to_open",
}


def reactivate_objects(objects, reason):
    """批量激活对象，并避免重复处理同一样品。"""
    validate_reason(reason)
    objects = unique_objects(objects)
    selected_sample_uids = set()
    reactivated_sample_uids = set()
    summaries = []

    for obj in objects:
        portal_type = getattr(obj, "portal_type", "")
        if portal_type in SAMPLE_PORTAL_TYPES:
            summaries.append(reactivate_sample(obj, reason))
            sample_uid = api.get_uid(obj)
            selected_sample_uids.add(sample_uid)
            reactivated_sample_uids.add(sample_uid)

    for obj in objects:
        portal_type = getattr(obj, "portal_type", "")
        if portal_type not in ANALYSIS_PORTAL_TYPES:
            continue
        sample = get_parent_sample(obj)
        sample_uid = sample and api.get_uid(sample) or None
        if sample_uid in selected_sample_uids:
            continue
        summaries.append(reactivate_analysis(
            obj,
            reason,
            reactivate_parent_sample=sample_uid not in reactivated_sample_uids))
        if sample_uid:
            reactivated_sample_uids.add(sample_uid)

    return summaries


def reactivate_sample(sample, reason):
    """重新激活样品，并联动其下测试和工作表。"""
    validate_reason(reason)

    transition_object(sample, "reactivate", reason)

    analyses = []
    worksheets = []
    seen_worksheets = set()
    for analysis in get_sample_analyses(sample):
        analyses.append(analysis)
        reactivate_analysis_object(analysis, reason)

        worksheet = get_analysis_worksheet(analysis)
        worksheet_uid = worksheet and api.get_uid(worksheet) or None
        if worksheet is None or worksheet_uid in seen_worksheets:
            continue
        rollback_worksheet(worksheet, reason)
        seen_worksheets.add(worksheet_uid)
        worksheets.append(worksheet)

    audit_reactivate(
        sample,
        target_type="sample",
        reason=reason,
        sample=sample,
        analyses=analyses,
        worksheets=worksheets,
    )
    reindex_related([sample] + analyses + worksheets)
    return {
        "sample_uid": api.get_uid(sample),
        "analysis_count": len(analyses),
        "worksheet_count": len(worksheets),
    }


def reactivate_analysis(analysis, reason, reactivate_parent_sample=True):
    """重新激活单条测试，并联动父样品和所属工作表。"""
    validate_reason(reason)

    sample = get_parent_sample(analysis)
    if (reactivate_parent_sample and sample is not None and
            api.get_review_status(sample) in ("verified", "published")):
        # 从分析项发起时，已审核和已发布样品都需要同步回退到 sample_received。
        transition_object(sample, "reactivate", reason)

    reactivate_analysis_object(analysis, reason)

    worksheet = get_analysis_worksheet(analysis)
    if worksheet is not None:
        rollback_worksheet(worksheet, reason)

    audit_reactivate(
        analysis,
        target_type="analysis",
        reason=reason,
        sample=sample,
        analyses=[analysis],
        worksheets=worksheet and [worksheet] or [],
    )
    related = [analysis]
    if sample is not None:
        related.append(sample)
    if worksheet is not None:
        related.append(worksheet)
    reindex_related(related)
    return {
        "sample_uid": sample and api.get_uid(sample) or None,
        "analysis_uids": [api.get_uid(analysis)],
        "worksheet_uids": worksheet and [api.get_uid(worksheet)] or [],
    }


def reactivate_analysis_object(analysis, reason):
    """分析项统一通过单一 Reactivate 回退到 assigned。"""
    transition_object(analysis, "reactivate", reason)


def rollback_worksheet(worksheet, reason):
    """仅在工作表处于待审核/已审核时回到 open。"""
    state = api.get_review_status(worksheet)
    if state == "verified":
        sync_worksheet_to_open(worksheet, reason, state)
        return
    transition_id = WORKSHEET_ROLLBACK_TRANSITIONS.get(state)
    if not transition_id:
        return
    # 待审核工作表官方支持 rollback_to_open，优先走原生 transition。
    transition_object(worksheet, transition_id, reason)


def sync_worksheet_to_open(worksheet, reason, source_state):
    """在无合法 transition 时，受控同步工作表状态到 open 并记录审计。"""
    # verified 工作表没有 rollback_to_open，而其 retract guard 又依赖子分析可 retract，
    # 在 reactivate 场景下这两个条件都不成立，只能走受控状态同步。
    changeWorkflowState(
        worksheet,
        WORKSHEET_WORKFLOW_ID,
        "open",
        trigger_events=False,
        action="reactivate_worksheet_sync",
    )
    store_reactivate_snapshot(
        worksheet,
        action="reactivate_worksheet_sync",
        actor=get_user_id(),
        reason=reason,
        source_state=source_state,
        target_state="open",
    )


def transition_object(obj, transition_id, reason):
    """执行工作流迁移，并透传审计备注。"""
    workflow_tool = api.get_tool("portal_workflow")
    try:
        workflow_tool.doActionFor(obj, transition_id, comment=reason)
    except WorkflowException as exc:
        message = normalize_workflow_error_message(exc, transition_id)
        raise RuntimeError(message)
    return obj


def normalize_workflow_error_message(error, action_id):
    """将工作流异常中的占位符替换为真实 transition 名称。"""
    message = str(error)
    return message.replace("${action_id}", action_id)


def audit_reactivate(root, target_type, reason, sample=None, analyses=None, worksheets=None):
    """在根对象上追加一条重激活汇总审计。"""
    analyses = analyses or []
    worksheets = worksheets or []
    metadata = {
        "action": "reactivate_audit",
        "actor": get_user_id(),
        "reason": reason,
        "target_type": target_type,
        "sample_uid": sample and api.get_uid(sample) or None,
        "analysis_uids": [api.get_uid(item) for item in analyses],
        "worksheet_uids": [api.get_uid(item) for item in worksheets],
    }
    store_reactivate_snapshot(root, **metadata)


def store_reactivate_snapshot(obj, **metadata):
    """写入带“重新激活原因”字段的审计快照，供原生 Changes diff 直接展示。"""
    reason = metadata.get("reason", u"")
    snapshot = take_snapshot(obj, store=False, **metadata)
    # 将原因写入快照正文而不是仅写 metadata，这样无需修改 core 页面也会进入 diff。
    snapshot[REACTIVATE_REASON_FIELD] = reason
    storage = get_storage(obj)
    storage.append(json.dumps(snapshot))
    return snapshot


def reindex_related(objects):
    """重建对象与审计索引。"""
    for obj in unique_objects(objects):
        if hasattr(obj, "reindexObject"):
            obj.reindexObject()
        reindex_object(obj)


def get_sample_analyses(sample):
    """兼容获取样品下所有测试对象。"""
    analyses = sample.getAnalyses(full_objects=True)
    analyses = list(analyses or [])
    return [
        analysis for analysis in analyses
        if getattr(analysis, "portal_type", "") in ANALYSIS_PORTAL_TYPES
    ]


def get_parent_sample(analysis):
    """兼容不同 Analysis 对象的父样品获取方式。"""
    if hasattr(analysis, "getRequest"):
        return analysis.getRequest()
    return None


def get_analysis_worksheet(analysis):
    """兼容获取测试所在工作表。"""
    if hasattr(analysis, "getWorksheet"):
        return analysis.getWorksheet()
    return None


def unique_objects(objects):
    """按 UID 去重，保持原顺序。"""
    values = OrderedDict()
    for obj in objects or []:
        uid = api.get_uid(obj)
        values[uid] = obj
    return values.values()


def validate_reason(reason):
    """激活原因必填，避免无法审计。"""
    if not api.is_string(reason):
        raise ValueError("Reactivate reason must be a string")
    if not reason.strip():
        raise ValueError("Reactivate reason is required")
    return reason
