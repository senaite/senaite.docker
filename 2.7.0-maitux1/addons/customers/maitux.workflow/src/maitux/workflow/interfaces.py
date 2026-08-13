# -*- coding: utf-8 -*-
"""模块所有 Marker Interface 定义

每个内容类型都对应一个 Marker Interface，用于：
  1. ZCML 注册时的 for="..." 定向
  2. 适配器查找
  3. 类型检查
"""

from zope.interface import Interface


class IWorkflowContainer(Interface):
    """示例容器接口 —— 标记 Workflow 根容器"""
