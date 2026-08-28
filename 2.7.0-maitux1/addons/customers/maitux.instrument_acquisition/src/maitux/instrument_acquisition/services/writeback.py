# -*- coding: utf-8 -*-
"""第一阶段统一保存回写服务

"统一保存"时，将当前分配关系写回 Worksheet 对应分析行的指定 Interim 字段：

- 只允许回写 `phase1_targets.PHASE1_TARGET_DEFINITIONS` 中定义的目标位
- 一条读数对应多个目标位时，多个目标位写入同一 event_id 来源（同源引用）
- 第一阶段只写 Interim 字段，不扩展普通结果字段
- 回写成功后更新 annotations 中的读数状态为 saved
"""

import json
import logging

from bika.lims import api

from maitux.instrument_acquisition.services.phase1_targets import PHASE1_KEYWORDS
from maitux.instrument_acquisition.services.phase1_targets import (
    is_array_result_type,
)
from maitux.instrument_acquisition.services.phase1_targets import (
    parse_target_key_full,
)
from maitux.instrument_acquisition.services.session_store import (
    SOURCE_MANUAL,
)
from maitux.instrument_acquisition.services.session_store import STATUS_SAVED
from maitux.instrument_acquisition.services.session_store import add_log
from maitux.instrument_acquisition.services.session_store import (
    commit_session_data,
)
from maitux.instrument_acquisition.services.session_store import get_session_data

logger = logging.getLogger("maitux.instrument_acquisition")


def _resolve_value(assignment, events):
    """从分配记录解析要回写的值

    - 手工填写来源：直接使用手工值
    - 读数来源：优先 parsed_value，回退到 raw_text
    """
    source = assignment.get("source")
    if source == SOURCE_MANUAL:
        return assignment.get("value")
    event_id = assignment.get("event_id")
    if not event_id:
        return None
    event = events.get(event_id)
    if not event:
        return None
    return event.get("parsed_value") or event.get("raw_text")


def _is_array_interim(analysis, keyword):
    """分析项的该关键字 interim 是否为数组类型（list/multiselect 等）"""
    try:
        for interim in (analysis.getInterimFields() or []):
            if interim.get("keyword") == keyword:
                return is_array_result_type(interim.get("result_type"))
    except Exception:
        pass
    return False


def write_interim(analysis, keyword, value):
    """将值写入分析项的指定 Interim Field

    数组类型（list/multiselect 等）：value 为 list，序列化为 JSON 数组
    字符串（如 '["1.234","2.345"]'，与 SENAITE multi-value interim 一致）；
    普通类型：value 为单值字符串。

    目标 Interim 不存在时自动追加。
    """
    if isinstance(value, (list, tuple)):
        clean = [api.safe_unicode(v) for v in value if v not in (None, u"")]
        value = json.dumps(clean, ensure_ascii=False)
    value = api.safe_unicode(value)
    interims = analysis.getInterimFields() or []
    updated = False
    for interim in interims:
        if interim.get("keyword") == keyword:
            interim["value"] = value
            updated = True
            break
    if not updated:
        interims.append({
            "keyword": keyword,
            "title": keyword,
            "value": value,
        })
    analysis.setInterimFields(interims)
    analysis.reindexObject()


def save(worksheet):
    """统一保存：将当前所有分配回写到 Worksheet 对应分析行的 Interim 字段

    数组类型字段（result_type=list/multiselect 等）：同一 (分析, 关键字)
    的所有行（含手动添加行）按序号收集为数组，写 JSON 数组字符串。

    :param worksheet: Worksheet 对象
    :returns: (success, message, details)
    """
    data = get_session_data(worksheet)
    assignments = data.get("assignments", {})
    events = data.get("events", {})

    # 按 (analysis_uid, keyword) 分组收集 (seq, value)
    groups = {}
    for target_key, assignment in assignments.items():
        analysis_uid, keyword, seq = parse_target_key_full(target_key)
        if not keyword or keyword not in PHASE1_KEYWORDS:
            continue
        value = _resolve_value(assignment, events)
        if value is None or value == u"":
            continue
        groups.setdefault((analysis_uid, keyword), []).append((seq, value))

    written = 0
    skipped = 0
    errors = []

    for (analysis_uid, keyword), items in groups.items():
        items.sort(key=lambda item: item[0])
        values = [value for _seq, value in items]

        try:
            analysis = api.get_object(analysis_uid)
            if not api.is_object(analysis):
                skipped += 1
                continue
            if _is_array_interim(analysis, keyword):
                # 数组字段：所有行写为一个 JSON 数组
                write_interim(analysis, keyword, values)
            else:
                # 普通字段：单值（取最后一行）
                write_interim(analysis, keyword, values[-1])
            written += 1
            # 同步更新读数状态
            for target_key, assignment in assignments.items():
                _uid, _kw, _seq = parse_target_key_full(target_key)
                if _uid == analysis_uid and _kw == keyword:
                    event_id = assignment.get("event_id")
                    if event_id and event_id in events:
                        events[event_id]["status"] = STATUS_SAVED
        except Exception as exc:
            errors.append(u"%s: %s" % (keyword, exc))
            logger.warn("Writeback failed for %s/%s: %s",
                        analysis_uid, keyword, exc)

    if errors:
        message = (u"回写完成：%s 个成功，%s 个跳过，%s 个失败。"
                   % (written, skipped, len(errors)))
        detail = u"失败明细：%s" % u"；".join(errors)
        add_log(worksheet, "save", message + detail)
        commit_session_data(worksheet, data)
        return False, message, {
            "written": written,
            "skipped": skipped,
            "errors": errors,
        }

    message = u"统一保存完成：已回写 %s 个目标位。" % written
    add_log(worksheet, "save", message)
    commit_session_data(worksheet, data)
    return True, message, {
        "written": written,
        "skipped": skipped,
        "errors": [],
    }
