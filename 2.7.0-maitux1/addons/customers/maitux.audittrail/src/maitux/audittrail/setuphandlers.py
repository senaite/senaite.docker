# -*- coding: utf-8 -*-
"""审计追踪增强安装/卸载处理器"""

from Products.CMFPlone.interfaces import INonInstallable
from senaite.core import logger
from zope.interface import implementer


PROJECTNAME = "maitux.audittrail"


@implementer(INonInstallable)
class HiddenProfiles(object):
    """隐藏卸载 Profile，保持 Add-ons 面板整洁。"""

    def getNonInstallableProfiles(self):  # noqa camelCase
        return [
            "%s:uninstall" % PROJECTNAME,
        ]

    def getNonInstallableProducts(self):  # noqa camelCase
        return []


def setup_handler(context):
    """标准插件安装入口。"""
    install_file = "%s.txt" % PROJECTNAME
    if context.readDataFile(install_file) is None:
        return

    logger.info("Maitux.Audittrail setup handler [BEGIN]")
    logger.info("Maitux.Audittrail setup handler [DONE]")


def import_various(context):
    """兼容旧入口，统一委托到标准安装入口。"""
    setup_handler(context)


def uninstall_handler(context):
    """标准插件卸载入口。"""
    uninstall_file = "%s-uninstall.txt" % PROJECTNAME
    if context.readDataFile(uninstall_file) is None:
        return

    logger.info("Maitux.Audittrail uninstall handler [BEGIN]")
    logger.info("Maitux.Audittrail uninstall handler [DONE]")
