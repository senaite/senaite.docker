# -*- coding: utf-8 -*-
"""Worksheets 列表视图适配器：底部工具栏注入「仪器采集」动作

使用 senaite.app.listing 官方提供的 `IListingViewAdapter` 订阅者扩展点：

- 不覆盖 WorksheetsView（避免 browser:page permission 依赖与 ZCML 加载顺序问题）
- 不依赖 browser layer（无需重导 profile）
- 任何 Worksheets 列表（含 review state 过滤页签）底部工具栏都会出现
  「仪器采集」按钮，点击后由 workflow action 适配器校验只能单选并进入采集页
"""

from zope.interface import implements

from senaite.app.listing.interfaces import IListingViewAdapter


ACQUISITION_TRANSITION_ID = "instrument_acquisition"


class ListingViewAdapter(object):
    """为 Worksheets 列表注入「仪器采集」底部动作按钮"""

    implements(IListingViewAdapter)

    def __init__(self, view, context):
        self.view = view
        self.context = context

    def before_render(self):
        transition = {
            "id": ACQUISITION_TRANSITION_ID,
            "title": u"仪器采集",
        }
        for review_state in self.view.review_states:
            review_state.setdefault("custom_transitions", []).append(transition)
        # 确保显示勾选列与底部工作流按钮区
        self.view.show_select_column = True
        self.view.show_workflow_action_buttons = True

    def folder_item(self, obj, item, index):
        return item
