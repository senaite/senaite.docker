# -*- coding: utf-8 -*-
"""Calculation Interim Fields 审计展示格式化工具"""

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
            "value": safe_text(row.get("value")),
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
