# -*- coding: utf-8 -*-
"""当前站点是否安装了本 addon —— 供进程级注册做站点级收口

背景：ZCML 注册是整个 Zope 实例级的，启动即生效；GenericSetup profile 的安装
是站点级的。两者不挂钩，于是本 addon 三处 ``for="*"`` 的进程级注册会在**所有**
站点生效，包括从没装过 maitux.esignature 的站点：

- ``guards/configure.zcml`` 的 IGuardAdapter：``bika.lims.workflow.guard_handler``
  用 ``getAdapters((instance,), IGuardAdapter)`` 遍历所有适配器，任一返回 False
  即否决整个 transition。
- ``guards/configure.zcml`` 的 IBeforeTransitionEvent 订阅器：会 raise
  WorkflowException，是真正把未安装站点拦死的那一环。
- ``adapters/configure.zcml`` 的 IActionSucceededEvent 订阅器：会往站点写签名
  记录和审计快照。

而且未安装站点并不是「规则表为空所以无害」：站点没有 registry 记录时
``SignaturePolicyResolver._registry_value`` 全部退回代码默认值，
``loads_policy_rules(u"[]", legacy_rule=...)`` 会退回那条 legacy pilot 规则，
于是 ``resolve(Analysis, "verify")`` 在每个站点都得到
``signature_required=True``（source=rules_table）。

IGuardAdapter 与这两个订阅器的查找签名里都没有 request，所以 ZCML 的
``layer=`` 绑定在这里用不上（那只对带 request 的多适配器有效）。
只能在处理函数内部做站点级判断，未安装则放行。
"""

try:
    from Products.CMFCore.utils import getToolByName
    from zope.component.hooks import getSite
except ImportError:  # pragma: no cover - 纯逻辑单测会在 Zope 之外加载本模块
    getToolByName = None
    getSite = None


PRODUCT_NAME = "maitux.esignature"
PROFILE_ID = "maitux.esignature:default"

# portal_setup 对没装过的 profile 返回字符串 "unknown"，装过则返回版本元组，
# 例如 (u'1000',)。
UNKNOWN_PROFILE_VERSION = "unknown"

# guard 求值在列表视图里是每行每 transition 一次，一个请求可能上百次，
# 所以判定结果按请求缓存。key 带上站点路径，避免同一请求跨站点时串味。
REQUEST_CACHE_KEY = "maitux.esignature.site_installed"

_MARKER = object()


def is_profile_version_installed(version):
    """纯判定：portal_setup 返回的 profile 版本是否代表「已安装」"""
    if not version:
        return False
    if isinstance(version, (tuple, list)):
        values = [item for item in version if item]
        if not values:
            return False
        return list(values) != [UNKNOWN_PROFILE_VERSION]
    return version != UNKNOWN_PROFILE_VERSION


def query_site_installed(site):
    """不带缓存地问一次站点：本 addon 的 profile 装了没有

    先问 portal_quickinstaller —— 它维护的是 Add-ons 面板安装/卸载的那份记录，
    也是判断「这个站点要不要本 addon」最贴切的语义。取不到再退回
    portal_setup 的 profile 版本。
    """
    if site is None:
        return False

    quickinstaller = getToolByName(site, "portal_quickinstaller", None)
    if quickinstaller is not None:
        try:
            return bool(quickinstaller.isProductInstalled(PRODUCT_NAME))
        except Exception:
            pass

    setup_tool = getToolByName(site, "portal_setup", None)
    if setup_tool is None:
        return False
    try:
        version = setup_tool.getLastVersionForProfile(PROFILE_ID)
    except Exception:
        return False
    return is_profile_version_installed(version)


def is_installed_in_current_site():
    """本 addon 是否安装在当前站点。取不到站点时按未安装处理（放行）。"""
    if getSite is None:
        return False

    site = getSite()
    if site is None:
        return False

    try:
        cache_key = "%s:%s" % (
            REQUEST_CACHE_KEY, "/".join(site.getPhysicalPath()))
    except Exception:
        cache_key = REQUEST_CACHE_KEY

    # 没有 request（脚本、定时任务）时 site.REQUEST 取不到，直接不缓存。
    request = getattr(site, "REQUEST", None)
    if request is not None:
        cached = getattr(request, "get", lambda k, d=None: d)(cache_key, _MARKER)
        if cached is not _MARKER:
            return cached

    installed = query_site_installed(site)

    if request is not None:
        try:
            request.set(cache_key, installed)
        except Exception:
            pass
    return installed
