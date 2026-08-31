# -*- coding: utf-8 -*-
"""profile v4 -> v5：让齿轮菜单那条入口走翻译。

v4 把标题改成了 ASCII 止血，但同时也去掉了 i18n:domain，于是界面上只能显示英文。
S13 补齐后半句：标题保持 ASCII msgid，加回 i18n:domain，由 locales/zh_CN 提供中文。
"""

import logging

logger = logging.getLogger("maitux.auditjournal")

PROFILE = "profile-maitux.auditjournal:default"


def upgrade(setup_tool):
    logger.warning("auditjournal: upgrade v4 -> v5, re-importing actions "
                   "(ASCII msgid + i18n domain, translated via locales)")
    setup_tool.runImportStepFromProfile(PROFILE, "actions")
    logger.warning("auditjournal: upgrade v4 -> v5 finished")
