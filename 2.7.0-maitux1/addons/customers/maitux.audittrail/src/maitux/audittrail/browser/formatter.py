# -*- coding: utf-8 -*-
"""Calculation Interim Fields 审计展示格式化工具"""

import json

try:
    from html import escape
except ImportError:
    from cgi import escape


RESULT_TYPE_TITLES = {
    "calculated": u"计算值",
    "numeric": u"数值",
    "string": u"字符串",
    "text": u"文本",
    "datetime": u"日期时间",
    "select": u"下拉选择",
    "multiselect": u"多选",
    "multiselect_duplicates": u"多选(可重复)",
    "multichoice": u"多项选择",
    "multivalue": u"多值",
}


try:
    text_type = unicode
except NameError:
    text_type = str


def safe_text(value):
    """把任意值转换为安全字符串，避免把 None 直接展示到页面"""
    if value is None:
        return u""
    if isinstance(value, text_type):
        return value
    try:
        return text_type(value)
    except Exception:
        return text_type(str(value))


def safe_html(value):
    """统一做 HTML 转义，避免公式中的特殊字符破坏页面结构"""
    return escape(safe_text(value), quote=True)


def is_truthy(value):
    """兼容 bool、字符串和数字等不同来源的真值判断"""
    if isinstance(value, bool):
        return value
    text = safe_text(value).strip().lower()
    return text in ("1", "true", "yes", "on")


def get_flag_text(item):
    """把多个布尔位压缩成一列，减少审计界面的横向宽度"""
    flags = []
    if is_truthy(item.get("allow_empty")):
        flags.append(u"允许空")
    if is_truthy(item.get("report")):
        flags.append(u"报告")
    if is_truthy(item.get("hidden")):
        flags.append(u"隐藏")
    if is_truthy(item.get("wide")) or is_truthy(item.get("apply_wide")):
        flags.append(u"全局应用")
    return u"，".join(flags) if flags else u"无"


def get_result_type_title(value):
    """把内部 result_type 转成更容易阅读的中文文案"""
    text = safe_text(value).strip()
    if not text:
        return u""
    return RESULT_TYPE_TITLES.get(text, text)


def item_to_dict(item):
    """把单行 Interim Field 转成字典

    快照中同一字段可能以两种结构存储：
    - 字典结构：{"keyword": "NM", ...}
    - 键值对列表结构：[["keyword", "NM"], ["unit", "g"], ...]
    """
    if isinstance(item, dict):
        return dict(item)
    if isinstance(item, (list, tuple)):
        # 兼容 [[key, value], ...] 键值对列表
        return {pair[0]: pair[1]
                for pair in item
                if isinstance(pair, (list, tuple)) and len(pair) >= 2}
    return {}


def format_default_value(value):
    """默认值可能是一段 JSON，直接显示会把中文露成 \\uXXXX 转义

    多选类型（list / multiselect / multichoice）的 interim 默认值在快照里是
    `json.dumps()` 的产物，而 `json.dumps` 默认 `ensure_ascii=True`，
    所以 "未知杂质" 存进去就成了 "\\u672a\\u77e5\\u6742\\u8d28"。
    数据本身没问题，是这里没解回来。

    只在看起来像 JSON 容器时才尝试解析；解析失败就原样返回，
    绝不能因为格式化把原始值弄丢 —— 这是审计记录。
    """
    if isinstance(value, (list, tuple)):
        return u"、".join([safe_text(item) for item in value])

    text = safe_text(value).strip()
    if not text or text[0] not in (u"[", u"{"):
        return text

    try:
        decoded = json.loads(text)
    except (ValueError, TypeError):
        return text

    if isinstance(decoded, (list, tuple)):
        return u"、".join([safe_text(item) for item in decoded])
    return safe_text(decoded)


def clean_no_value(value):
    """把快照中的 <NO_VALUE> 占位符转成空串，避免界面出现噪音"""
    text = safe_text(value).strip()
    if text.upper() in ("<NO_VALUE>", "NO_VALUE"):
        return u""
    return text


def normalize_rows(value):
    """只提取审计页面真正关心的字段，屏蔽原始 JSON 噪音"""
    rows = []
    if not isinstance(value, (list, tuple)):
        return rows

    for item in value:
        row = item_to_dict(item)
        if not row:
            continue
        rows.append({
            "keyword": safe_text(row.get("keyword")),
            "title": safe_text(row.get("title")),
            "result_type": get_result_type_title(row.get("result_type")),
            "value": format_default_value(row.get("value")),
            "formula": clean_no_value(row.get("formula")),
            "unit": safe_text(row.get("unit")),
            "choices": safe_text(row.get("choices")),
            "flags": get_flag_text(row),
        })
    return rows


def render_interim_fields_html(value):
    """把 Interim Fields 渲染成可读表格，替代原始 JSON 串"""
    rows = normalize_rows(value)
    if not rows:
        return u'<span class="audit-interim-empty">未设置</span>'

    header = u"""
<table class="table table-condensed table-bordered audit-interim-table">
  <thead>
    <tr>
      <th>关键字</th>
      <th>字段标题</th>
      <th>结果类型</th>
      <th>默认值</th>
      <th>公式</th>
      <th>单位</th>
      <th>选项</th>
      <th>标志</th>
    </tr>
  </thead>
  <tbody>
""".strip()

    body = []
    for row in rows:
        body.append(u"""
    <tr>
      <td>{keyword}</td>
      <td>{title}</td>
      <td>{result_type}</td>
      <td>{value}</td>
      <td>{formula}</td>
      <td>{unit}</td>
      <td>{choices}</td>
      <td>{flags}</td>
    </tr>
""".format(
            keyword=safe_html(row["keyword"]),
            title=safe_html(row["title"]),
            result_type=safe_html(row["result_type"]),
            value=safe_html(row["value"]),
            formula=safe_html(row["formula"]),
            unit=safe_html(row["unit"]),
            choices=safe_html(row["choices"]),
            flags=safe_html(row["flags"]),
        ).strip())

    footer = u"""
  </tbody>
</table>
""".strip()

    return u"\n".join([header] + body + [footer])


# --------------------------------------------------------------------------
# 电子签名（maitux.esignature）在审计追踪页面的呈现
#
# 21 CFR Part 11 §11.50(b) 要求签名 manifestation 是"电子记录任何人类可读形式"
# 的组成部分。签名数据一直写在快照的 __metadata__ 里，但原生 SENAITE 的审计
# 列表没有任何一列去渲染它 —— 记了却从不显示，本身即不满足条款。
#
# 这里只读 metadata 的字典键，不 import maitux.esignature：
# 没装 esignature 的站点取不到键，该列恒为空，不构成反向依赖。
# --------------------------------------------------------------------------

SIGNATURE_SUMMARY_PREFIX = u"Electronic signature"


def parse_signature_summary(text):
    """解析 esignature 写进 comments 的 "k=v; k=v" 摘要

    这个回落分支是必需的，不是锦上添花：结构化的 metadata["esignature"] 受
    签名策略的 auditlog_summary_enabled 门控，该开关关掉时字典根本不会写，
    只剩 DCWorkflow 带过来的这条摘要字符串。
    """
    summary = safe_text(text).strip()
    if not summary.startswith(SIGNATURE_SUMMARY_PREFIX):
        return None

    data = {}
    for piece in summary.split(u";"):
        key, sep, value = piece.strip().partition(u"=")
        if not sep:
            continue
        data[key.strip()] = value.strip()
    if not data:
        return None

    return {
        "signer": data.get(u"first_signer", u""),
        "countersigner": data.get(u"second_signer", u""),
        "meaning": data.get(u"meaning", u""),
        "reason": data.get(u"reason", u""),
        "require_countersign": data.get(u"countersign_required") == u"yes",
        "auth_backend": data.get(u"auth_backend", u""),
    }


def signature_from_metadata(esignature):
    """从结构化的 metadata["esignature"] 取签名信息"""
    if not isinstance(esignature, dict):
        return None
    if not esignature.get("enabled", True):
        return None

    return {
        "signer": safe_text(
            esignature.get("primary_signer_user_id")
            or esignature.get("initiator_user_id")
            or esignature.get("user_id")
        ),
        "countersigner": safe_text(esignature.get("countersigner_user_id")),
        "meaning": safe_text(esignature.get("meaning")),
        "reason": safe_text(esignature.get("reason")),
        "require_countersign": bool(esignature.get("require_countersign")),
        "auth_backend": safe_text(esignature.get("auth_backend_id")),
    }


def extract_signature(metadata):
    """优先取结构化字典，回落到 comments 摘要；都没有则返回 None"""
    if not isinstance(metadata, dict):
        return None
    data = signature_from_metadata(metadata.get("esignature"))
    if data:
        return data
    return parse_signature_summary(metadata.get("comments"))


def render_signature_html(data, timestamp=None):
    """把签名渲染成人类可读的几行；无签名的行返回空串"""
    if not data:
        return u""

    lines = []

    def add(label, value):
        value = safe_text(value).strip()
        if value:
            lines.append((label, value))

    # §11.50(a) 要求的三要素：签名人姓名、签署日期时间、签名含义。
    # 时间与同一行的"修改时间"列同源，这里重复一次是刻意的 ——
    # manifestation 应当自身完整，不依赖读者去横向对齐别的列。
    add(u"签名人", data.get("signer"))
    add(u"签名时间", timestamp)
    add(u"含义", data.get("meaning"))
    add(u"原因", data.get("reason"))
    if data.get("require_countersign"):
        add(u"复核人", data.get("countersigner") or u"（待复核）")
    add(u"验证方式", data.get("auth_backend"))

    if not lines:
        return u""

    rows = [
        u'<div class="audit-signature-line">'
        u'<span class="audit-signature-label">{}：</span>'
        u'<span class="audit-signature-value">{}</span>'
        u'</div>'.format(safe_html(label), safe_html(value))
        for label, value in lines
    ]
    return u'<div class="audit-signature">{}</div>'.format(u"".join(rows))
