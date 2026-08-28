# -*- coding: utf-8 -*-
from zope.interface import Interface

from maitux.reviewerassignment.interfaces import IReviewerAssignmentLayer


class IInstrumentParsingTemplates(Interface):
    pass


class IInstrumentParsingTemplate(Interface):
    pass


class IInstrumentAcquisitionLayer(IReviewerAssignmentLayer):
    """仪器采集浏览器层

    继承 maitux.reviewerassignment 的浏览器层，保证：
    - 本模块对 `manage_results` 的覆盖优先级高于 reviewerassignment 现有实现
    - reviewerassignment 的审核人扩展功能不丢失（layer 叠加，不修改旧模块）

    第一阶段的 annotations key、采集状态常量见
    `maitux.instrument_acquisition.services.phase1_targets`。
    """
