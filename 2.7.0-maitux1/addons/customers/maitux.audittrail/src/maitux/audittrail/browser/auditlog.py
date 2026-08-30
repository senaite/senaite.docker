# -*- coding: utf-8 -*-
"""审计追踪增强视图"""

import collections
import json

import six
from Products.Five.browser.pagetemplatefile import ViewPageTemplateFile
from bika.lims import api
from bika.lims.api.snapshot import _process_value
from bika.lims.api.snapshot import compare_snapshots
from bika.lims.api.snapshot import get_snapshot_by_version
from bika.lims.api.snapshot import get_snapshot_metadata
from bika.lims.api.snapshot import get_snapshots
from bika.lims.browser.auditlog import AuditLogView as BaseAuditLogView

from maitux.audittrail.browser.formatter import extract_signature
from maitux.audittrail.browser.formatter import render_interim_fields_html
from maitux.audittrail.browser.formatter import render_signature_html


SIGNATURE_COLUMN_ID = "esignature"


class AuditLogView(BaseAuditLogView):
    """覆盖原审计追踪页，提升 Interim Fields 的可读性并呈现电子签名"""

    diff_template = ViewPageTemplateFile("templates/auditlog_diff.pt")

    def __init__(self, context, request):
        super(AuditLogView, self).__init__(context, request)
        self.columns = self.add_signature_column(self.columns)
        # ★ 必须两处都改。基类 __init__ 里是
        #       "columns": self.columns.keys()
        #   Python 2 的 .keys() 返回的是列表快照，只往 self.columns 塞新键
        #   不会传导到这里，列不会出现 —— 静默失败。
        for review_state in self.review_states:
            review_state["columns"] = self.columns.keys()

    def add_signature_column(self, columns):
        """在"工作流状态"之后插入签名列

        刻意不设 toggle：默认可见。21 CFR Part 11 §11.50(b) 要求签名
        manifestation 是人类可读形式的组成部分，藏进"显示列"里等人勾选不算已呈现。
        """
        column = {
            "title": u"电子签名",
            "sortable": False,
        }
        new_columns = collections.OrderedDict()
        for key, value in columns.items():
            new_columns[key] = value
            if key == "review_state":
                new_columns[SIGNATURE_COLUMN_ID] = column
        # 上游若改了列名导致锚点找不到，也要保证这一列存在，只是位置退到最后
        if SIGNATURE_COLUMN_ID not in new_columns:
            new_columns[SIGNATURE_COLUMN_ID] = column
        return new_columns

    def is_interim_fields(self, field, value):
        """只对 Calculation/Analysis 的 InterimFields 做结构化展示

        兼容快照里大小写两种字段名：InterimFields（Calculation）与
        interim_fields（Analysis 等 SuperModel 生成的小写字段名）。
        """
        field = (field or "").lower()
        return field in ("interimfields", "interim_fields") and \
            isinstance(value, (list, tuple))

    def render_text_value(self, value):
        """复用原生的人类可读字符串转换逻辑"""
        return _process_value(value)

    def render_html_value(self, field, value):
        """InterimFields 输出结构化 HTML，其它字段保持普通文本"""
        if self.is_interim_fields(field, value):
            return render_interim_fields_html(value)
        return api.text_to_html(self.render_text_value(value), wrap="pre")

    def render_diff(self, diff):
        """先把 diff 预处理成模板更容易消费的结构"""
        rows = []
        for field in diff.keys():
            row = {
                "field": field,
                "label": self.get_widget_label_for(field, default=field),
                "is_interim_fields": False,
                "diffs": [],
            }
            for current_value, previous_value in diff[field]:
                is_interim = self.is_interim_fields(field, current_value) or \
                    self.is_interim_fields(field, previous_value)
                row["is_interim_fields"] = is_interim
                row["diffs"].append({
                    "before_text": self.render_text_value(previous_value),
                    "after_text": self.render_text_value(current_value),
                    "before_html": self.render_html_value(field, previous_value),
                    "after_html": self.render_html_value(field, current_value),
                })
            rows.append(row)
        return self.diff_template(self, rows=rows)

    def folderitems(self):
        """复制原逻辑，仅把 diff 改成 raw=True 以拿到原始结构"""
        items = []
        snapshots = get_snapshots(self.context)
        snapshots = list(reversed(snapshots))
        self.total = len(snapshots)
        batch = snapshots[self.limit_from:self.limit_from + self.pagesize]

        for num, snapshot in enumerate(batch):
            item = self.make_empty_item(**snapshot)
            version = self.total - self.limit_from - num - 1
            item["version"] = version

            snapshot_data = json.dumps(snapshot, indent=2, sort_keys=True)
            item["snapshot"] = api.text_to_html(snapshot_data, wrap="pre")

            metadata = get_snapshot_metadata(snapshot)
            m_date = metadata.get("modified")
            item["modified"] = self.to_localized_time(m_date)

            actor = metadata.get("actor")
            item["actor"] = actor

            properties = api.get_user_properties(actor)
            item["fullname"] = properties.get("fullname", actor)

            roles = metadata.get("roles", [])
            if not isinstance(roles, (list, tuple)):
                roles = [roles] if roles else []
            roles = [role for role in roles if isinstance(role, six.string_types)]
            item["roles"] = ", ".join(roles)

            item["remote_address"] = metadata.get("remote_address")
            item["action"] = self.translate_state(metadata.get("action"))

            review_state = metadata.get("review_state")
            item["review_state"] = self.translate_state(review_state)

            # 电子签名：优先取结构化的 metadata["esignature"]，
            # 回落到 DCWorkflow 带过来的 comments 摘要；无签名的行留空。
            item[SIGNATURE_COLUMN_ID] = render_signature_html(
                extract_signature(metadata), timestamp=item["modified"])

            prev_snapshot = get_snapshot_by_version(self.context, version - 1)
            if prev_snapshot:
                prev_metadata = get_snapshot_metadata(prev_snapshot)
                prev_review_state = prev_metadata.get("review_state")
                if prev_review_state != review_state:
                    item["replace"]["review_state"] = "{} &rarr; {}".format(
                        self.translate_state(prev_review_state),
                        self.translate_state(review_state))

                # 这里显式改用 raw=True，保留 InterimFields 的列表/字典结构，
                # 便于后续在模板里按表格方式渲染。
                diff = compare_snapshots(snapshot, prev_snapshot, raw=True)
                item["diff"] = self.render_diff(diff)

            items.append(item)

        return items
