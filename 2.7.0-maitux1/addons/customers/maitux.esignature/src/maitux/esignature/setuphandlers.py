# -*- coding: utf-8 -*-
"""GenericSetup handlers for the electronic signature add-on."""

from senaite.core import logger
from plone.registry.interfaces import IRegistry
from Products.CMFPlone.interfaces import INonInstallable
from zope.component import getUtility
from zope.interface import implementer

from maitux.esignature.interfaces import IESignatureControlPanelSettings


REGISTRY_PREFIX = "maitux.esignature"
PROJECTNAME = "maitux.esignature"


@implementer(INonInstallable)
class HiddenProfiles(object):
    """隐藏卸载 Profile，保持 Add-ons 面板整洁。"""

    def getNonInstallableProfiles(self):  # noqa camelCase
        return [
            "%s:uninstall" % PROJECTNAME,
        ]

    def getNonInstallableProducts(self):  # noqa camelCase
        return []


def register_registry_defaults():
    """按接口注册默认 registry，避免旧站点导入 registry.xml 报错。"""
    registry = getUtility(IRegistry)
    registry.registerInterface(
        IESignatureControlPanelSettings,
        prefix=REGISTRY_PREFIX,
    )


def setup_handler(context):
    """标准插件安装入口。"""
    install_file = "%s.txt" % PROJECTNAME
    if context.readDataFile(install_file) is None:
        return

    logger.info("MAITUX E-Signature setup handler [BEGIN]")
    register_registry_defaults()
    logger.info("MAITUX E-Signature setup handler [DONE]")


def import_various(context):
    """兼容旧入口，统一委托到标准安装入口。"""
    setup_handler(context)


def uninstall_handler(context):
    """标准插件卸载入口。"""
    uninstall_file = "%s-uninstall.txt" % PROJECTNAME
    if context.readDataFile(uninstall_file) is None:
        return

    logger.info("MAITUX E-Signature uninstall handler [BEGIN]")
    logger.info("MAITUX E-Signature uninstall handler [DONE]")
