# -*- coding: utf-8 -*-
"""profile v2 -> v3：把「审计流水」入口加进齿轮菜单。

这是本包**第一个有实际内容的 upgrade step** —— S10 建的那条通道在这里第一次
派上真实用场（此前 v1->v2 是空 step，只为验证通道本身）。
"""

import logging

logger = logging.getLogger("maitux.auditjournal")

PROFILE = "profile-maitux.auditjournal:default"


def upgrade(setup_tool):
    logger.warning("auditjournal: upgrade v2 -> v3, importing actions")
    setup_tool.runImportStepFromProfile(PROFILE, "actions")
    logger.warning("auditjournal: upgrade v2 -> v3 finished "
                   "(audit journal entry added to the user/gear menu)")
