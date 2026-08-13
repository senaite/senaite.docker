# -*- coding: utf-8 -*-
from bika.lims import api
from Products.CMFPlone.interfaces import INonInstallable
from senaite.core import logger
from senaite.core.setuphandlers import add_dexterity_items
from zope.interface import implementer

PROJECTNAME = "maitux.instrument_acquisition"


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

    logger.info("MAITUX Instrument Acquisition setup handler [BEGIN]")
    run_install_steps()
    logger.info("MAITUX Instrument Acquisition setup handler [DONE]")


def run_install_steps():
    """执行安装步骤。"""
    setup = api.get_senaite_setup()
    add_dexterity_items(
        setup,
        [
            (
                "instrumentparsingtemplates",
                "Instrument Parsing Templates",
                "InstrumentParsingTemplates",
            ),
        ],
    )


def post_install(context):
    """兼容旧入口。"""
    logger.info("MAITUX Instrument Acquisition post install handler [BEGIN]")
    run_install_steps()
    logger.info("MAITUX Instrument Acquisition post install handler [DONE]")


def uninstall_handler(context):
    """标准插件卸载入口。"""
    uninstall_file = "%s-uninstall.txt" % PROJECTNAME
    if context.readDataFile(uninstall_file) is None:
        return

    logger.info("MAITUX Instrument Acquisition uninstall handler [BEGIN]")
    logger.info("MAITUX Instrument Acquisition uninstall handler [DONE]")


def uninstall(context):
    """兼容旧入口。"""
    logger.info("MAITUX Instrument Acquisition uninstall handler [BEGIN]")
    logger.info("MAITUX Instrument Acquisition uninstall handler [DONE]")

