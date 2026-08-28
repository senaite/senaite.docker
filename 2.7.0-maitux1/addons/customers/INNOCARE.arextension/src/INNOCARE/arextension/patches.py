# -*- coding: utf-8 -*-
import logging
from bika.lims.browser.analysisrequest.add2 import AnalysisRequestAddView

logger = logging.getLogger("INNOCARE.arextension")

# 运行时站点判断：addon 的 browserlayer 是否在当前站点注册。
# monkey patch 是进程级副作用，无法按站点隔离；在每个 patch 内运行时判断，
# layer 未注册的站点回退原方法，还原原生行为。
_AR_EXTENSION_LAYER_ID = (
    "INNOCARE.arextension.extenders.analysisrequest.IARExtensionLayer"
)


def _is_enabled():
    """判断当前站点是否启用了本 addon。

    default profile 的 browserlayer.xml 注册 ``IARExtensionLayer``；站点
    安装该 profile 后 layer 进入本地 browserlayer 注册表。这里据此判断：
    layer 已注册 => 应用补丁；否则回退原方法。无法判定（无站点/异常）时
    保守视为启用，保持既有行为。
    """
    try:
        from zope.component.hooks import getSite
        from plone.browserlayer import utils as _layer_utils
        site = getSite()
        if site is None:
            return True
        for layer in _layer_utils.registered_layers():
            if getattr(layer, "__identifier__", None) == _AR_EXTENSION_LAYER_ID:
                return True
        return False
    except Exception:
        return True


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
        # 原生 str 若含非 ASCII（如 setup 面板的中文标题），zope.i18n.translate
        # 会按 ascii 解码 msgid 而抛 UnicodeDecodeError，此类直接返回原生结果。
        if isinstance(msgid, str):
            try:
                msgid.decode("ascii")
            except UnicodeDecodeError:
                return result
        context = kwargs.get("context") or _bika_api.get_request()
        for domain in _EXTRA_TRANSLATION_DOMAINS:
            try:
                translated = _ztranslate(msgid, domain=domain, context=context)
            except Exception:
                # 附加域查找异常不得影响主流程（如排序/翻译）
                continue
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
    if not _is_enabled():
        return widget
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


# ---------------------------------------------------------------------------
# 去除 AR 接收（receive）前的强制“采样日期（Date Sampled）”校验
# senaite 核心的 receive 守卫位于
#   bika.lims.workflow.analysisrequest.guards.guard_receive
# 其逻辑是：只有当 sample.getDateSampled() 有值时，guard_handler 才放行
# “receive” 过渡，否则“样品接收”动作不显示。
# 本项目未启用采样流程，接收入口不应强制要求录入采样日期，故恒放行。
# guard_handler 在每次求值时通过 getattr(模块, 'guard_receive') 取函数，
# 因此只要替换该模块属性即可生效。
# ---------------------------------------------------------------------------
from bika.lims.workflow.analysisrequest import guards as _ar_workflow_guards

# 保留原方法引用，便于排查/回退
_original_ar_guard_receive = _ar_workflow_guards.guard_receive


def patched_ar_guard_receive(sample):
    """允许在未填写采样日期的情况下接收 AR"""
    if not _is_enabled():
        return _original_ar_guard_receive(sample)
    return True


_ar_workflow_guards.guard_receive = patched_ar_guard_receive
logger.info("Patched guard_receive -> always True (Date Sampled not required for receive)")


# ---------------------------------------------------------------------------
# 隐藏 AR 编辑/查看页顶部“无法接收/请设置采样日期”的黄色提示横幅
# 来源：senaite.core.browser.viewlets.sample.not_sampled.NotSampledViewlet
# 该视图在“未接收 且 未填 DateSampled”时无条件展示，会误导操作者，
# 本项目未启用采样流程，故直接置为不显示。
# ---------------------------------------------------------------------------
from senaite.core.browser.viewlets.sample.not_sampled import NotSampledViewlet

_original_not_sampled_is_visible = NotSampledViewlet.is_visible


def patched_not_sampled_is_visible(self):
    """隐藏未采集提示横幅"""
    if not _is_enabled():
        return _original_not_sampled_is_visible(self)
    return False


NotSampledViewlet.is_visible = patched_not_sampled_is_visible
logger.info("Patched NotSampledViewlet.is_visible -> False (hide 'not sampled' warning banner)")


def restore_all():
    """还原本模块注入的全部 monkey patch（幂等，供 uninstall 调用）。

    只做行为还原，绝不触碰业务数据。每个 patch 先判断当前是否仍指向
    本模块的 patched 版本，避免误覆盖其它代码后续的修改。
    """
    restored = []

    # 1) senaite.core.i18n.translate：撤销 addon-domain 回退
    if getattr(_senaite_i18n, "translate", None) is patched_senaite_translate:
        _senaite_i18n.translate = _original_senaite_translate
        restored.append("senaite_translate")
    try:
        import senaite.core.browser.viewlets.sidebar as _sidebar_mod
        if getattr(_sidebar_mod, "translate", None) is patched_senaite_translate:
            _sidebar_mod.translate = _original_senaite_translate
    except ImportError:
        pass

    # 2) get_input_widget：恢复右侧控件自动标签
    if getattr(AnalysisRequestAddView, "get_input_widget", None) \
            is patched_get_input_widget:
        AnalysisRequestAddView.get_input_widget = _original_get_input_widget
        restored.append("get_input_widget")

    # 3) guard_receive：恢复原生接收守卫（重新要求采样日期）
    if getattr(_ar_workflow_guards, "guard_receive", None) \
            is patched_ar_guard_receive:
        _ar_workflow_guards.guard_receive = _original_ar_guard_receive
        restored.append("guard_receive")

    # 4) NotSampledViewlet.is_visible：恢复未采样提示横幅
    if getattr(NotSampledViewlet, "is_visible", None) \
            is patched_not_sampled_is_visible:
        NotSampledViewlet.is_visible = _original_not_sampled_is_visible
        restored.append("NotSampledViewlet.is_visible")

    logger.info("INNOCARE.arextension restore_all: restored %s", restored)
    return restored
