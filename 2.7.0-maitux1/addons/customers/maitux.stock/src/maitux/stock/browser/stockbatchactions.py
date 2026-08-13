# -*- coding: utf-8 -*-
from bika.lims import api

from maitux.stock.stockbatchexpiry import REVIEW_STATE_DESTROYED
from maitux.stock.stockbatchexpiry import REVIEW_STATE_EXPIRED
from maitux.stock.stockbatchexpiry import get_review_state
from maitux.stock.stockbatchexpiry import is_due_for_expiry


ACTION_CONSUME = "stockbatch_consume"
ACTION_SPLIT = "stockbatch_split"
ACTION_RETURN = "stockbatch_return"
ACTION_DESTROY = "stockbatch_destroy"
ACTION_STOCKTAKE = "stockbatch_stocktake"
ACTION_PRINT = "stockbatch_print"

ACTION_TITLES = {
    ACTION_CONSUME: u"Consume",
    ACTION_SPLIT: u"Split",
    ACTION_RETURN: u"Return",
    ACTION_DESTROY: u"Destroy",
    ACTION_STOCKTAKE: u"Stocktake",
    ACTION_PRINT: u"Print Labels",
}

ACTION_CSS_CLASSES = {
    ACTION_CONSUME: u"btn btn-success",
    ACTION_SPLIT: u"btn btn-primary",
    ACTION_RETURN: u"btn btn-warning",
    ACTION_DESTROY: u"btn btn-danger",
    ACTION_STOCKTAKE: u"btn btn-primary",
    ACTION_PRINT: u"btn btn-outline-secondary",
}

ALL_ACTION_IDS = (
    ACTION_CONSUME,
    ACTION_SPLIT,
    ACTION_RETURN,
    ACTION_DESTROY,
    ACTION_STOCKTAKE,
    ACTION_PRINT,
)

ACTIVE_ACTION_IDS = (
    ACTION_CONSUME,
    ACTION_SPLIT,
    ACTION_RETURN,
    ACTION_DESTROY,
    ACTION_STOCKTAKE,
    ACTION_PRINT,
)

EXPIRED_ACTION_IDS = (
    ACTION_DESTROY,
    ACTION_PRINT,
)

DESTROYED_ACTION_IDS = (
    ACTION_PRINT,
)

STATE_ALLOWED_ACTION_IDS = {
    u"active": ACTIVE_ACTION_IDS,
    REVIEW_STATE_EXPIRED: EXPIRED_ACTION_IDS,
    REVIEW_STATE_DESTROYED: DESTROYED_ACTION_IDS,
}


def get_effective_batch_status(batch, now=None):
    """返回批次的有效动作状态。"""
    review_state = api.safe_unicode(get_review_state(batch) or u"").strip()
    if review_state == REVIEW_STATE_DESTROYED:
        return REVIEW_STATE_DESTROYED
    # 中文注释：All 页签要把“已到期但工作流还没同步”的批次按 expired 处理，
    # 这样前端按钮与后端业务限制保持一致。
    if review_state == REVIEW_STATE_EXPIRED or is_due_for_expiry(batch, now=now):
        return REVIEW_STATE_EXPIRED
    return u"active"


def get_allowed_action_ids_for_statuses(statuses, selection_count=None):
    """根据一组状态求动作交集。"""
    normalized = []
    for status in statuses or []:
        status = api.safe_unicode(status or u"").strip() or u"active"
        normalized.append(status if status in STATE_ALLOWED_ACTION_IDS else u"active")

    if not normalized:
        allowed = list(ALL_ACTION_IDS)
    else:
        allowed = set(STATE_ALLOWED_ACTION_IDS.get(normalized[0], ACTIVE_ACTION_IDS))
        for status in normalized[1:]:
            allowed &= set(STATE_ALLOWED_ACTION_IDS.get(status, ACTIVE_ACTION_IDS))
        allowed = [action_id for action_id in ALL_ACTION_IDS if action_id in allowed]

    # 中文注释：分装页面当前只支持单个源批次，多选时即使都是 active 也不能放行。
    if selection_count is not None and int(selection_count) != 1:
        allowed = [action_id for action_id in allowed if action_id != ACTION_SPLIT]
    return allowed


def get_allowed_action_ids_for_batches(batches, now=None):
    """根据所选批次计算允许显示/执行的动作。"""
    batches = [batch for batch in (batches or []) if api.is_object(batch)]
    statuses = [get_effective_batch_status(batch, now=now) for batch in batches]
    return get_allowed_action_ids_for_statuses(
        statuses,
        selection_count=len(batches),
    )


def get_transition_items_for_action_ids(action_ids):
    """把动作 ID 列表转换成标准 listing 需要的 transition 数据。"""
    transitions = []
    for action_id in action_ids or []:
        title = ACTION_TITLES.get(action_id)
        if not title:
            continue
        transition = {
            "id": action_id,
            "title": title,
        }
        css_class = ACTION_CSS_CLASSES.get(action_id)
        # 中文注释：listing 会直接读取 transition 的 css_class 来渲染按钮颜色，
        # 这里补回颜色映射，避免按钮全部退回默认灰色样式。
        if css_class:
            transition["css_class"] = css_class
        transitions.append(transition)
    return transitions


def get_transition_items_for_batch(batch, now=None):
    """返回单个批次在标准 listing 中可显示的 transition 列表。"""
    status = get_effective_batch_status(batch, now=now)
    action_ids = get_allowed_action_ids_for_statuses([status], selection_count=1)
    return get_transition_items_for_action_ids(action_ids)


def get_batches_from_uids(uids):
    """把 UID 列表安全转换为批次对象列表。"""
    batches = []
    for uid in uids or []:
        if not api.is_uid(uid):
            continue
        batch = api.get_object_by_uid(uid, default=None)
        if not api.is_object(batch):
            continue
        if api.get_portal_type(batch) != "StockBatch":
            continue
        batches.append(batch)
    return batches


def is_action_allowed_for_uids(action_id, uids, now=None):
    """判断所选 UID 集合是否允许执行目标动作。"""
    batches = get_batches_from_uids(uids)
    if not batches:
        return False
    allowed = get_allowed_action_ids_for_batches(batches, now=now)
    return action_id in allowed
