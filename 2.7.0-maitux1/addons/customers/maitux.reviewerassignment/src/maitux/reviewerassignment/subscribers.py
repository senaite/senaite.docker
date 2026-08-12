# -*- coding: utf-8 -*-
"""事件订阅处理器

在对象创建、修改、删除等生命周期事件发生时自动执行的逻辑。
"""

from bika.lims import api
from senaite.core import logger


# ============ 示例订阅器（可按需启用） ============

# def on_object_added(obj, event):
#     """当 Reviewerassignment 对象被创建时自动触发"""
#     portal_type = getattr(obj, "portal_type", None)
#     if portal_type != "YourType":
#         return
#     # 自动填充元数据
#     logger.info("Maitux.Reviewerassignment: 新对象已创建 %s" % api.get_id(obj))
