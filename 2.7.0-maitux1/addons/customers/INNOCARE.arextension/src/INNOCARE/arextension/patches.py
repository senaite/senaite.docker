# -*- coding: utf-8 -*-
import logging
from collections import OrderedDict
from bika.lims.browser.analysisrequest.add2 import AnalysisRequestAddView

logger = logging.getLogger("INNOCARE.arextension")

# 保存原生的方法，以防其他地方还需要调用
_original_get_points_of_capture = AnalysisRequestAddView.get_points_of_capture

def patched_get_points_of_capture(self):
    """
    拦截原生的 get_points_of_capture，
    在返回给前台模板前，强行将 'field' 移除，从而在 UI 上隐藏 Field Analyses 区块
    """
    pocs = _original_get_points_of_capture(self)
    
    # pocs 是一个 OrderedDict，例如 OrderedDict([('field', 'Field Analyses'), ('lab', 'Lab Analyses')])
    if 'field' in pocs:
        # 删除 field 键值对
        del pocs['field']
        
    return pocs

# 注入补丁
AnalysisRequestAddView.get_points_of_capture = patched_get_points_of_capture
logger.info("Patched AnalysisRequestAddView.get_points_of_capture to hide Field Analyses")


# ---------------------------------------------------------------------------
# SENAITE i18n translate 附加域回退
# SENAITE sidebar 渲染时对文件夹标题调用 senaite.core.i18n.translate(str)，
# 而 str 无 domain，原生只查 "senaite.core" 域（见 i18n.py translate 默认值）。
# 自定义 addon 的文件夹标题（Projects / Sample Properties 等）在
# senaite.core 域没有翻译条目 -> 菜单只显示英文。
# 此处做附加域回退：默认域未命中的纯字符串，再按各 addon 域查找。
# 仅影响"未命中"路径，不影响带 domain 的 Message 与已命中翻译。
# ---------------------------------------------------------------------------
from zope.i18n import translate as _ztranslate
from zope.i18nmessageid import Message
from bika.lims import api as _bika_api

import senaite.core.i18n as _senaite_i18n

_EXTRA_TRANSLATION_DOMAINS = (
    "maitux.projects",
    "maitux.hazardcategories",
    "maitux.roles",
)

_original_senaite_translate = _senaite_i18n.translate


def patched_senaite_translate(msgid, to_utf8=True, **kwargs):
    result = _original_senaite_translate(msgid, to_utf8=to_utf8, **kwargs)
    # Message 对象自带 domain，走原生逻辑；仅处理纯字符串未命中场景
    if not isinstance(msgid, Message) and result == msgid:
        context = kwargs.get("context") or _bika_api.get_request()
        for domain in _EXTRA_TRANSLATION_DOMAINS:
            translated = _ztranslate(msgid, domain=domain, context=context)
            if translated != msgid:
                return _bika_api.to_utf8(translated) if to_utf8 else translated
    return result


_senaite_i18n.translate = patched_senaite_translate

# 若 senaite.core.browser.viewlets.sidebar 已加载旧引用，同步替换
try:
    import senaite.core.browser.viewlets.sidebar as _sidebar_mod
    _sidebar_mod.translate = patched_senaite_translate
except ImportError:
    pass

logger.info("Patched senaite.core.i18n.translate with addon-domain fallback")


# ---------------------------------------------------------------------------
# AR 新增页右侧控件去重标签
# ar_add2.pt 的左侧标签列（field-label）已用原始 widget 渲染字段名+备注；
# 但 Archetypes 原生 widgets/selection.pt 的 select 分支会无条件在控件上方
# 再渲染一次 label + description，导致右侧出现重复的 "样品回收/是否回收样品"。
# 由于 render_own_label 对此模板无效，故在 get_input_widget 中对复制后用于
# 右侧渲染的 widget 清空 label/description，仅保留左侧标签列显示。
# 仅作用于本 addon 管控的字段，不影响其它原生字段。
# ---------------------------------------------------------------------------
_original_get_input_widget = AnalysisRequestAddView.get_input_widget

# 需要在右侧控件中隐藏自动标签的字段（左侧标签列仍显示字段名+备注）
_RIGHT_CLEAN_LABEL_FIELDS = ("SampleRecovery", "SafetyPrecautions")


def patched_get_input_widget(self, fieldname, arnum=0, **kw):
    widget = _original_get_input_widget(self, fieldname, arnum=arnum, **kw)
    base_fieldname = str(fieldname).split("-")[0]
    if base_fieldname in _RIGHT_CLEAN_LABEL_FIELDS:
        # 右侧控件由"复制字段"渲染，其 widget 与原字段 widget 不同实例。
        # 置空复制字段 widget 的 label/description，左侧标签列（用原字段
        # widget）不受影响。
        context = self.get_ar()
        base_field = context.getField(base_fieldname)
        copied_field = context.getField(self.get_fieldname(base_field, arnum))
        copied_field.widget.label = ""
        copied_field.widget.description = ""
    return widget


AnalysisRequestAddView.get_input_widget = patched_get_input_widget
logger.info("Patched AnalysisRequestAddView.get_input_widget to hide right-cell widget label")
